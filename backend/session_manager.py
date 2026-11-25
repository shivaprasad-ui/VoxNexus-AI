import time, uuid

SESSIONS = {}   # in memory: lost when the server restarts (uvicorn --reload restarts it on every file save)


def create(speaker_id):
    sid = "S-" + uuid.uuid4().hex[:8]
    SESSIONS[sid] = {
        "session_id": sid,
        "speaker_id": speaker_id,
        "trust_score": 0,
        "status": "UNVERIFIED",      # UNVERIFIED, VERIFIED, SUSPENDED
        "verification_count": 0,
        "last_identity_check": None,
        "events": [],
    }
    return SESSIONS[sid]


def get(sid):
    if sid not in SESSIONS:
        raise KeyError(sid)
    return SESSIONS[sid]


def log(session, kind, detail):
    session["events"].append({"time": time.strftime("%H:%M:%S"), "kind": kind, "detail": detail})