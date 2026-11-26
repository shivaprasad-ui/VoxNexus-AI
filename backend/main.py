import logging
import os
import secrets

from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

import admin
import auth
import customer
import firewall
import schema
import session_manager

BASE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="VoxNexus AI")
schema.migrate()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(admin.router)


def _page(request: Request, role: str, filename: str):
    """Serve a portal page only to a logged-in user of that role, else send them to the login page."""
    tok = request.cookies.get(auth.COOKIE[role])
    u = auth._lookup(tok) if tok else None
    if not u or u["role"] != role:
        return RedirectResponse("/login", status_code=303)
    return FileResponse(os.path.join(BASE, filename), headers={"Cache-Control": "no-store"})


@app.get("/")
def home():
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
def health():
    return {"message": "VoxNexus AI is running"}


@app.get("/login")
def login_page():
    return FileResponse(os.path.join(BASE, "login.html"), headers={"Cache-Control": "no-store"})


@app.get("/ui")
def old_ui():
    return RedirectResponse("/login", status_code=303)


@app.get("/customer")
def customer_page(request: Request):
    return _page(request, "customer", "customer.html")


@app.get("/admin")
def admin_page(request: Request):
    return _page(request, "admin", "admin.html")


@app.post("/protect")
def protect(sid: str = Form(...), action: str = Form(...), x_api_key: str = Header("")):
    """TrustBridge: for other bank systems. Needs the TRUSTBRIDGE_KEY service key, not a browser login."""
    key = os.environ.get("TRUSTBRIDGE_KEY", "")
    if not key:
        raise HTTPException(503, "TrustBridge is disabled (no TRUSTBRIDGE_KEY is set).")
    if not secrets.compare_digest(x_api_key.encode(), key.encode()):
        raise HTTPException(401, "Invalid API key.")
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session")
    decision, reason = firewall.enforce(sid, s, action)
    if decision != "ALLOW":
        raise HTTPException(403, f"{decision}: {reason}")
    return {"status": f"'{action}' allowed", "sid": sid}


try:
    import intent_engine
    intent_engine.analyze("warm up")
except (ImportError, OSError) as error:
    logging.getLogger(__name__).warning("Intent model warm-up skipped: %s", error)
