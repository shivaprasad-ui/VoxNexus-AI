"""Customer API. Every route needs a customer login. Customer id and speaker id come from the database."""
import logging
import os
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import audit
import callguard
import challenge
import detectif
import firewall
import permissions
import schema
import session_manager
import transaction_guard as tg
import trust_engine
from auth import require_customer
from callguard import analyze as callguard_analyze
from common import api_call, check_wav_length, db
from parsers import parse_aletheia, parse_eidos

router = APIRouter(prefix="/api/customer")
BASE = os.path.dirname(os.path.abspath(__file__))
PENDING_DIR = os.path.join(BASE, "pending_enrollments")
_log = logging.getLogger(__name__)


def _own(sid, u):
    """Return the in-memory session only if it belongs to this customer."""
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session")
    if s.get("customer_id") != u["id"]:
        schema.log_event("ACCESS_DENIED", u["id"], sid, severity="high",
                         detail="tried to use another customer's session")
        raise HTTPException(403, "Access denied.")
    return s


def _latest(cid):
    mine = [s for s in session_manager.SESSIONS.values() if s.get("customer_id") == cid]
    return max(mine, key=lambda s: s.get("started_at", 0)) if mine else None


def _view(s):
    """Only what the browser needs. Internal fields stay on the server."""
    return {
        "session_id": s["session_id"],
        "status": s["status"],
        "trust_score": s["trust_score"],
        "effective_trust": trust_engine.effective_score(s),
        "pressure_cap": s.get("pressure_cap", 100),
        "last_identity_check": s.get("last_identity_check"),
        "events": s["events"][-30:],
    }


def _enroll_state(cid):
    with db() as c:
        usable = c.execute(
            "SELECT 1 FROM voice_enrollments WHERE customer_id = ? AND status = 'APPROVED' LIMIT 1",
            (cid,)).fetchone() is not None
        last = c.execute(
            "SELECT status FROM voice_enrollments WHERE customer_id = ? ORDER BY id DESC LIMIT 1",
            (cid,)).fetchone()
    pending = last is not None and last["status"] == "PENDING"
    if pending:
        status = "PENDING"
    elif usable:
        status = "APPROVED"
    else:
        status = last["status"] if last else "NOT_ENROLLED"
    return {"status": status, "usable": usable, "pending": pending}


def _speaker(cid):
    with db() as c:
        r = c.execute("SELECT speaker_id FROM users WHERE id = ?", (cid,)).fetchone()
    return r["speaker_id"] if r else None


def _balance(cid):
    with db() as c:
        r = c.execute("SELECT balance FROM accounts WHERE customer_id = ?", (cid,)).fetchone()
    return r["balance"] if r else 0


# ---------------- dashboard, history ----------------

@router.get("/dashboard")
def dashboard(u: dict = Depends(require_customer)):
    with db() as c:
        txns = c.execute(
            "SELECT id, amount, recipient, status, created_at FROM transactions "
            "WHERE customer_id = ? ORDER BY created_at DESC LIMIT 8", (u["id"],)).fetchall()
    s = _latest(u["id"])
    return {
        "name": u["full_name"],
        "customer_id": u["id"],
        "balance": _balance(u["id"]),
        "enrollment": _enroll_state(u["id"]),
        "session": _view(s) if s else None,
        "transactions": [dict(t) for t in txns],
    }


@router.get("/history")
def history(u: dict = Depends(require_customer)):
    with db() as c:
        rows = c.execute(
            "SELECT ts, event_type, severity, detail, session_id FROM security_events "
            "WHERE customer_id = ? ORDER BY id DESC LIMIT 80", (u["id"],)).fetchall()
    return [dict(r) for r in rows]


# ---------------- voice enrollment (needs admin confirmation) ----------------

@router.post("/enroll")
def enroll(file: UploadFile = File(...), u: dict = Depends(require_customer)):
    data = file.file.read()
    check_wav_length(data, min_seconds=15)
    import speech_gate
    if not speech_gate.has_speech(data):
        raise HTTPException(400, "No speech detected in this recording.")
    with db() as c:
        if c.execute("SELECT 1 FROM voice_enrollments WHERE customer_id = ? AND status = 'PENDING'",
                     (u["id"],)).fetchone():
            raise HTTPException(409, "You already have an enrollment waiting for admin confirmation.")
        row = c.execute("SELECT speaker_id FROM users WHERE id = ?", (u["id"],)).fetchone()
        spk = (row["speaker_id"] if row else None) or "vx_" + u["id"].lower().replace("-", "")
        cur = c.execute(
            "INSERT INTO voice_enrollments (customer_id, speaker_id, status, created_at) VALUES (?,?,?,?)",
            (u["id"], spk, "PENDING", time.time()))
        eid = cur.lastrowid
    try:
        os.makedirs(PENDING_DIR, exist_ok=True)
        with open(os.path.join(PENDING_DIR, "%d.wav" % eid), "wb") as f:
            f.write(data)
    except OSError:
        with db() as c:
            c.execute("DELETE FROM voice_enrollments WHERE id = ?", (eid,))
        raise HTTPException(500, "Could not store the recording.")
    schema.log_event("ENROLL_SUBMITTED", u["id"], detail="enrollment %d waiting for admin" % eid)
    return {"enrollment_id": eid, "status": "PENDING",
            "message": "Submitted. A bank admin must confirm it before it is used."}


# ---------------- session ----------------

@router.post("/session/start")
def session_start(u: dict = Depends(require_customer)):
    if not _enroll_state(u["id"])["usable"]:
        raise HTTPException(403, "Your voice enrollment has not been confirmed by a bank admin yet.")
    spk = _speaker(u["id"])
    if not spk:
        raise HTTPException(403, "No speaker id is registered for this customer.")
    with db() as c:
        c.execute("UPDATE sessions SET ended_at = ? WHERE customer_id = ? AND ended_at IS NULL",
                  (time.time(), u["id"]))
    s = session_manager.create(spk, u["id"])
    s["role"] = "customer"          # set by the server, never by the browser
    session_manager.sync(s)
    schema.log_event("SESSION_STARTED", u["id"], s["session_id"])
    return _view(s)


@router.get("/session/{sid}")
def session_view(sid: str, u: dict = Depends(require_customer)):
    return _view(_own(sid, u))


@router.post("/session/{sid}/check")
def session_check(
    sid: str,
    mode: str = Form("full"),
    action: str = Form("transfer_money"),
    challenge_id: str = Form(""),
    spoken: str = Form(""),
    file: UploadFile = File(...),
    u: dict = Depends(require_customer),
):
    s = _own(sid, u)
    if mode not in ("full", "monitor"):
        raise HTTPException(400, "mode must be 'full' or 'monitor'.")
    if action not in trust_engine.REQUIRED:
        raise HTTPException(400, "Unknown action.")
    if s["status"] == "SUSPENDED":
        raise HTTPException(403, "Session suspended. No more checks are accepted.")
    data = file.file.read()
    check_wav_length(data)
    import speech_gate
    if not speech_gate.has_speech(data):
        raise HTTPException(422, "No speech detected in this clip. Nothing was sent to DetectifAI.")
    audio = (file.filename, data, file.content_type)
    a = parse_aletheia(api_call(detectif.detect, audio))
    match, identity_checked, eidos = None, False, None
    if mode == "full" and a["fake"] is not True:
        e = parse_eidos(api_call(detectif.verify, s["speaker_id"], audio))
        match, identity_checked = e["match"], True
        eidos = {"match": e["match"], "similarity": e.get("similarity"), "threshold": e.get("threshold")}
    trust_engine.update(s, a["fake"], match, identity_checked)

    cid = u["id"]
    if a["fake"] is True:
        schema.log_event("FAKE_VOICE", cid, sid, severity="high", detail="Aletheia score %s" % a["score"])
    if identity_checked and match is False:
        schema.log_event("SPEAKER_MISMATCH", cid, sid, severity="high", detail="Eidos: speaker does not match")
    if s["status"] == "SUSPENDED" and not s.get("incident_logged"):
        import database
        database.incident(s["speaker_id"], s["events"][-1]["detail"])
        s["incident_logged"] = True
        schema.log_event("SESSION_SUSPENDED", cid, sid, severity="high", detail=s["events"][-1]["detail"])

    challenge_result = None
    if challenge_id:
        challenge_result = challenge.record_result(
            sid, challenge_id, spoken, mode == "full" and s["status"] == "VERIFIED")
    audit.log(sid, "check", mode=mode, status=s["status"],
              trust=trust_engine.effective_score(s), aletheia_score=a["score"])
    decision, reason = trust_engine.authorize(s, action)
    session_manager.sync(s)
    return {
        "decision": decision,
        "reason": reason,
        "trust": trust_engine.effective_score(s),
        "status": s["status"],
        "aletheia_score": a["score"],
        "eidos": eidos,
        "events": s["events"][-30:],
        "challenge": challenge_result,
    }


# ---------------- Call Guard ----------------

@router.post("/callguard")
def callguard_route(text: str = Form(...), voice_score: str = Form(""), sid: str = Form(""),
                    u: dict = Depends(require_customer)):
    s = _own(sid, u) if sid else None
    text = text[:4000]
    try:
        vs = float(voice_score) if voice_score != "" else None
    except ValueError:
        vs = None
    result = callguard_analyze(text, vs)
    try:
        import intent_engine
        ml = intent_engine.analyze(" ".join(text.split()[-30:]))
        result["ml"] = {"scam_score": round(ml["scam_score"], 2),
                        "label": "scam-like" if ml["scam_score"] >= 0.5 else "normal-like"}
    except (ImportError, OSError):
        result["ml"] = None
    result["penalty"] = 0
    result["new_signals"] = []
    if sid:
        callguard.mark_checked(sid, text)
        result.update(callguard.apply_penalty(sid, s, result["heard"], result.get("repeat_units", 0)))
        if result.get("new_signals"):
            schema.log_event("SCAM_SIGNAL", u["id"], sid, severity="warn",
                             detail=", ".join(result["new_signals"]))
        session_manager.sync(s)
    return result


@router.post("/detect")
def detect(file: UploadFile = File(...), u: dict = Depends(require_customer)):
    data = file.file.read()
    check_wav_length(data)
    return api_call(detectif.detect, (file.filename, data, file.content_type))


# ---------------- transfers ----------------

@router.post("/txn/prepare")
def txn_prepare(sid: str = Form(...), amount: int = Form(...), recipient: str = Form(...),
                u: dict = Depends(require_customer)):
    s = _own(sid, u)
    if not permissions.allowed(s.get("role", "customer"), "transfer_money"):
        raise HTTPException(403, "You are not allowed to transfer money.")
    if amount > _balance(u["id"]):
        raise HTTPException(400, "Insufficient balance.")
    try:
        t = tg.prepare(s, amount, recipient)
    except ValueError as e:
        schema.log_event("TXN_BLOCKED", u["id"], sid, severity="warn", detail=str(e))
        raise HTTPException(400, str(e))
    ch = challenge.issue(sid, t["id"]) if t["challenge_required"] else None
    session_manager.sync(s)     # makes sure the sessions row exists before the transaction row
    with db() as c:
        c.execute("UPDATE transactions SET status = 'SUPERSEDED' WHERE session_id = ? AND status = 'PREPARED'",
                  (sid,))
        c.execute(
            "INSERT INTO transactions (id, customer_id, session_id, amount, recipient, status, "
            "challenge_required, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (t["id"], u["id"], sid, t["amount"], t["recipient"], "PREPARED",
             1 if t["challenge_required"] else 0, time.time(), time.time() + t["expires_in"]))
    schema.log_event("TXN_PREPARED", u["id"], sid, t["id"], detail="%s to %s" % (t["amount"], t["recipient"]))
    return {"txn": t, "challenge": ch}


@router.post("/txn/challenge")
def txn_challenge(sid: str = Form(...), txn_id: str = Form(...), u: dict = Depends(require_customer)):
    s = _own(sid, u)
    t = s.get("pending_transfer")
    if not t or t["id"] != txn_id:
        raise HTTPException(404, "No pending transaction.")
    return challenge.issue(sid, txn_id)


@router.post("/txn/confirm")
def txn_confirm(sid: str = Form(...), txn_id: str = Form(...), u: dict = Depends(require_customer)):
    s = _own(sid, u)
    cid = u["id"]
    decision, reason = firewall.enforce(sid, s, "transfer_money")
    if decision != "ALLOW":
        schema.log_event("TXN_BLOCKED", cid, sid, txn_id, "warn", reason)
        raise HTTPException(403, f"{decision}: {reason}")
    p = s.get("pending_transfer")
    if p and p.get("id") == txn_id and p.get("amount", 0) > _balance(cid):
        raise HTTPException(400, "Insufficient balance.")
    try:
        out = tg.execute(s, txn_id)
    except ValueError as e:
        schema.log_event("TXN_BLOCKED", cid, sid, txn_id, "warn", str(e))
        raise HTTPException(403, str(e))
    session_manager.log(s, "TXN_APPROVED", "%s to %s" % (out["amount"], out["recipient"]))
    with db() as c:
        cur = c.execute("UPDATE accounts SET balance = balance - ? WHERE customer_id = ? AND balance >= ?",
                        (out["amount"], cid, out["amount"]))
        debited = cur.rowcount == 1
        c.execute("UPDATE transactions SET status = 'COMPLETED', executed_at = ? WHERE id = ?",
                  (time.time(), txn_id))
    if not debited:
        schema.log_event("TXN_DEBIT_FAILED", cid, sid, txn_id, "high", "balance changed during execution")
        raise HTTPException(409, "Balance changed during the transfer. Contact the bank.")
    schema.log_event("TXN_COMPLETED", cid, sid, txn_id, detail="%s to %s" % (out["amount"], out["recipient"]))
    session_manager.sync(s)
    return {**out, "balance": _balance(cid)}