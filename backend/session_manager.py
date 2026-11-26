import logging
import time
import uuid

SESSIONS = {}   # in memory: lost when the server restarts. A copy is mirrored to SQLite by sync().
_log = logging.getLogger(__name__)


def create(speaker_id, customer_id=None):
    sid = "S-" + uuid.uuid4().hex[:8]
    SESSIONS[sid] = {
        "session_id": sid,
        "speaker_id": speaker_id,
        "customer_id": customer_id,
        "started_at": time.time(),
        "trust_score": 0,
        "status": "UNVERIFIED",      # UNVERIFIED, VERIFIED, SUSPENDED
        "verification_count": 0,
        "last_identity_check": None,
        "events": [],
        "_events_synced": 0,
    }
    return SESSIONS[sid]


def get(sid):
    if sid not in SESSIONS:
        raise KeyError(sid)
    return SESSIONS[sid]


def log(session, kind, detail):
    session["events"].append({"time": time.strftime("%H:%M:%S"), "kind": kind, "detail": detail})


def _severity(kind):
    k = str(kind).upper()
    if "SUSPEND" in k or "FAKE" in k:
        return "high"
    if any(w in k for w in ("FAIL", "RETRY", "MISMATCH", "CALL_GUARD", "UNCERTAIN")):
        return "warn"
    return "info"


def sync(s):
    """Write the session row and any new events to SQLite. Never raises into the voice flow."""
    cid = s.get("customer_id")
    if not cid:
        return
    try:
        import schema
        score = s.get("trust_score", 0)
        try:
            import trust_engine
            score = trust_engine.effective_score(s)
        except Exception:
            pass
        c = schema.connect()
        try:
            c.execute(
                "INSERT INTO sessions (id, customer_id, started_at, status, trust_score) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status = excluded.status, trust_score = excluded.trust_score",
                (s["session_id"], cid, s.get("started_at", time.time()), s["status"], int(score)))
            n = s.get("_events_synced", 0)
            for e in s["events"][n:]:
                c.execute(
                    "INSERT INTO security_events (ts, customer_id, session_id, event_type, severity, detail) "
                    "VALUES (?,?,?,?,?,?)",
                    (time.time(), cid, s["session_id"], "ENGINE_" + str(e.get("kind")),
                     _severity(e.get("kind")), str(e.get("detail"))[:500]))
            s["_events_synced"] = len(s["events"])
        finally:
            c.close()
    except Exception:
        _log.exception("session sync failed")