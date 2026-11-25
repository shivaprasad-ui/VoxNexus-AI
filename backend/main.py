import io
import json
from sys import audit
import wave
import audit
import firewall
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import requests

from fastapi import Header
import detectif
import session_manager
import trust_engine
from parsers import parse_aletheia, parse_eidos
from risk_engine import assess
from authority import decide

app = FastAPI(title="VoxNexus AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_wav_length(data: bytes, min_seconds: float = 4):
    """Check clip length locally so invalid clips don't cost credits."""
    try:
        with wave.open(io.BytesIO(data)) as wav_file:
            seconds = wav_file.getnframes() / wav_file.getframerate()
    except Exception:
        raise HTTPException(400, "Please upload a .wav file.")
    if seconds < min_seconds or seconds > 120:
        raise HTTPException(
            400,
            f"Clip is {seconds:.1f}s. Please upload a clip between {min_seconds:.0f} and 120 seconds.",
        )


def api_call(fn, *args):
    try:
        return fn(*args)
    except detectif.ApiError as error:
        try:
            response = json.loads(error.text)
            api_error = response.get("error")
            message = api_error.get("message") if isinstance(api_error, dict) else None
        except (json.JSONDecodeError, AttributeError, TypeError):
            message = None
        raise HTTPException(error.status, message if isinstance(message, str) else error.text)
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502, detail=f"Could not reach DetectifAI: {error}"
        )


@app.get("/")
def home():
    return {"message": "VoxNexus AI is running"}


@app.post("/detect")
def detect(file: UploadFile = File(...)):
    data = file.file.read()
    check_wav_length(data)
    return api_call(detectif.detect, (file.filename, data, file.content_type))


@app.get("/ui")
def ui():
    return FileResponse("index.html")


@app.post("/enroll")
def enroll(speaker_id: str = Form(...), file: UploadFile = File(...)):
    data = file.file.read()
    check_wav_length(data, min_seconds=15)
    audio = (file.filename, data, file.content_type)
    raw = api_call(detectif.enroll, speaker_id, audio)
    return {"enrolled": speaker_id, "raw": raw}


@app.post("/analyze")
def analyze(
    speaker_id: str = Form(...),
    action: str = Form("transfer_money"),
    file: UploadFile = File(...),
):
    data = file.file.read()
    check_wav_length(data)
    audio = (file.filename, data, file.content_type)

    eidos = parse_eidos(api_call(detectif.verify, speaker_id, audio))
    aletheia = parse_aletheia(api_call(detectif.detect, audio))
    level, reason = assess(aletheia["fake"], eidos["match"])
    decision, next_step = decide(level, action)

    return {
        "risk_level": level,
        "reason": reason,
        "decision": decision,
        "next_step": next_step,
        "aletheia": aletheia,
        "eidos": eidos,
    }


@app.post("/session/start")
def session_start(speaker_id: str = Form(...), role: str = Form("customer")):
    s = session_manager.create(speaker_id)
    s["role"] = role
    return s


@app.get("/session/{sid}")
def session_view(sid: str):
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session")
    return {**s, "effective_trust": trust_engine.effective_score(s)}


@app.post("/session/{sid}/check")
def session_check(
    sid: str,
    mode: str = Form("full"),
    action: str = Form("transfer_money"),
    file: UploadFile = File(...),
):
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session")
    if s["status"] == "SUSPENDED":
        raise HTTPException(403, "Session suspended. No more checks are accepted.")

    data = file.file.read()
    check_wav_length(data)
    audio = (file.filename, data, file.content_type)

    a = parse_aletheia(api_call(detectif.detect, audio))
    match, identity_checked = None, False
    if mode == "full" and a["fake"] is not True:
        e = parse_eidos(api_call(detectif.verify, s["speaker_id"], audio))
        match, identity_checked = e["match"], True

    trust_engine.update(s, a["fake"], match, identity_checked)
    audit.log(sid, "check", mode=mode, status=s["status"],
        trust=trust_engine.effective_score(s), aletheia_score=a["score"])
    decision, reason = trust_engine.authorize(s, action)
    return {
        "decision": decision,
        "reason": reason,
        "trust": trust_engine.effective_score(s),
        "status": s["status"],
        "aletheia_score": a["score"],
        "events": s["events"],
    }


@app.post("/bank/transfer")
def transfer(sid: str = Form(...), amount: int = Form(...)):
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session")
    decision, reason = trust_engine.authorize(s, "transfer_money")
    decision, reason = firewall.enforce(sid, s, "transfer_money")
    if decision != "ALLOW":
        raise HTTPException(403, f"{decision}: {reason}")
    return {"status": "Transfer executed (mock)", "amount": amount}

@app.get("/audit")
def audit_view(sid: str | None = None):
    return audit.read(sid)

from typing import Optional



@app.post("/protect")
def protect(sid: str = Form(...), action: str = Form(...)):
    try:
        s = session_manager.get(sid)
    except KeyError:
        raise HTTPException(404, "Unknown session")
    decision, reason = firewall.enforce(sid, s, action)
    if decision != "ALLOW":
        raise HTTPException(403, f"{decision}: {reason}")
    return {"status": f"'{action}' allowed", "sid": sid}

