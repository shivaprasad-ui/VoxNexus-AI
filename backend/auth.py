"""Authentication: Argon2 passwords, server-side login sessions, role checks from the database."""
import hashlib
import os
import secrets
import sqlite3
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Form, HTTPException, Request, Response

import schema

router = APIRouter()
ph = PasswordHasher()
_DUMMY = ph.hash("not-a-real-password")  # makes unknown-user logins take similar time

IDLE_TTL = int(os.environ.get("LOGIN_IDLE_SECONDS", 20 * 60))
ABS_TTL = int(os.environ.get("LOGIN_MAX_SECONDS", 8 * 3600))
MAX_FAILS = 5
LOCK_SECONDS = 300
COOKIE = {"customer": "vx_customer", "admin": "vx_admin"}
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"  # set to 1 when served over HTTPS
GENERIC = "Invalid username or password."


def _hash_token(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


def create_user(username, password, role, full_name, speaker_id=None, balance=0):
    if role not in ("customer", "admin"):
        raise ValueError("Invalid role.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    uname = username.strip()
    if not uname:
        raise ValueError("Username is required.")
    uid = ("C-" if role == "customer" else "A-") + secrets.token_hex(3).upper()
    now = time.time()
    c = schema.connect()
    try:
        c.execute("BEGIN")
        try:
            c.execute(
                "INSERT INTO users (id, username, password_hash, role, full_name, speaker_id, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (uid, uname, ph.hash(password), role, full_name, speaker_id, now),
            )
            if role == "customer":
                c.execute(
                    "INSERT INTO accounts (id, customer_id, balance, created_at) VALUES (?,?,?,?)",
                    ("ACC-" + secrets.token_hex(4).upper(), uid, int(balance), now),
                )
            c.execute("COMMIT")
        except sqlite3.IntegrityError:
            c.execute("ROLLBACK")
            raise ValueError("Username or speaker id already exists.")
    finally:
        c.close()
    return uid


def _lookup(token):
    """Return the user for a valid login token, else None. The role is read from the users table."""
    h = _hash_token(token)
    now = time.time()
    c = schema.connect()
    try:
        r = c.execute(
            "SELECT l.created_at, l.expires_at, l.last_seen, u.id, u.username, u.role, "
            "u.full_name, u.speaker_id, u.active "
            "FROM login_sessions l JOIN users u ON u.id = l.user_id "
            "WHERE l.token_hash = ? AND l.revoked = 0",
            (h,),
        ).fetchone()
        if r is None or not r["active"]:
            return None
        if now > r["expires_at"] or now - r["last_seen"] > IDLE_TTL:
            c.execute("UPDATE login_sessions SET revoked = 1 WHERE token_hash = ?", (h,))
            return None
        c.execute("UPDATE login_sessions SET last_seen = ? WHERE token_hash = ?", (now, h))
        return {
            "id": r["id"], "username": r["username"], "role": r["role"],
            "full_name": r["full_name"], "speaker_id": r["speaker_id"],
        }
    finally:
        c.close()


def _user_for(request, role):
    tok = request.cookies.get(COOKIE[role])
    u = _lookup(tok) if tok else None
    if u is None:
        raise HTTPException(401, "Please log in.")
    if u["role"] != role:
        raise HTTPException(403, "This account is not allowed here.")
    return u


def require_customer(request: Request):
    return _user_for(request, "customer")


def require_admin(request: Request):
    return _user_for(request, "admin")


@router.post("/auth/login")
def login(response: Response, username: str = Form(...), password: str = Form(...)):
    uname = username.strip()[:64]
    now = time.time()
    c = schema.connect()
    try:
        c.execute("DELETE FROM login_sessions WHERE expires_at < ?", (now - 86400,))
        u = c.execute("SELECT * FROM users WHERE username = ?", (uname,)).fetchone()
        if u is None or not u["active"]:
            try:
                ph.verify(_DUMMY, password)
            except Exception:
                pass
            schema.log_event("LOGIN_FAILED", severity="warn", detail="unknown or inactive user")
            raise HTTPException(401, GENERIC)
        if u["locked_until"] > now:
            raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
        try:
            ph.verify(u["password_hash"], password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            fails = u["failed_logins"] + 1
            if fails >= MAX_FAILS:
                c.execute("UPDATE users SET failed_logins = 0, locked_until = ? WHERE id = ?",
                          (now + LOCK_SECONDS, u["id"]))
                schema.log_event("LOGIN_LOCKED", u["id"], severity="high", detail="too many failures")
            else:
                c.execute("UPDATE users SET failed_logins = ? WHERE id = ?", (fails, u["id"]))
                schema.log_event("LOGIN_FAILED", u["id"], severity="warn", detail="wrong password")
            raise HTTPException(401, GENERIC)

        c.execute("UPDATE users SET failed_logins = 0, locked_until = 0 WHERE id = ?", (u["id"],))
        if ph.check_needs_rehash(u["password_hash"]):
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (ph.hash(password), u["id"]))
        token = secrets.token_urlsafe(32)
        c.execute(
            "INSERT INTO login_sessions (token_hash, user_id, created_at, expires_at, last_seen) "
            "VALUES (?,?,?,?,?)",
            (_hash_token(token), u["id"], now, now + ABS_TTL, now),
        )
        schema.log_event("LOGIN_OK", u["id"], detail=u["role"])
        role = u["role"]
        response.set_cookie(COOKIE[role], token, httponly=True, samesite="strict",
                            secure=COOKIE_SECURE, max_age=ABS_TTL, path="/")
        return {"role": role, "name": u["full_name"],
                "redirect": "/customer" if role == "customer" else "/admin"}
    finally:
        c.close()


@router.post("/auth/logout")
def logout(request: Request, response: Response, portal: str = Form(...)):
    if portal not in COOKIE:
        raise HTTPException(400, "Unknown portal.")
    tok = request.cookies.get(COOKIE[portal])
    if tok:
        c = schema.connect()
        try:
            c.execute("UPDATE login_sessions SET revoked = 1 WHERE token_hash = ?", (_hash_token(tok),))
        finally:
            c.close()
    response.delete_cookie(COOKIE[portal], path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(portal: str, request: Request):
    if portal not in COOKIE:
        raise HTTPException(400, "Unknown portal.")
    u = _user_for(request, portal)
    return {"id": u["id"], "username": u["username"], "name": u["full_name"], "role": u["role"]}