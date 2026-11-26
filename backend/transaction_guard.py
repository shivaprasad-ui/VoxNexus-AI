import secrets, time, threading
import callguard, challenge, trust_engine
from database import transfer as db_transfer

TTL = 120              # approval expires after 2 minutes
NEED = 90              # same bar as trust_engine.REQUIRED["transfer_money"]
MAX_AMOUNT = 100000
SECOND_APPROVAL_OVER = 50000
LOCK = threading.RLock()
PRESSURE_MSG = ("Call Guard heard pressure tactics, so transfers are blocked for this "
                "session. Next step: call the customer back on the number on file.")


def public(t):
    return {"id": t["id"], "amount": t["amount"], "recipient": t["recipient"],
            "challenge_required": t["challenge_required"],
            "needs_approval": t["needs_approval"], "approved": t["approved"],
            "expires_in": max(0, int(t["expires"] - time.time()))}


def prepare(s, amount, recipient):
    recipient = (recipient or "").strip()
    if not (0 < amount <= MAX_AMOUNT) or not recipient:
        raise ValueError("Enter an amount up to %d and a recipient." % MAX_AMOUNT)
    if s["status"] == "SUSPENDED":
        raise ValueError("Session is suspended.")
    if s.get("pressure_cap", 100) < NEED:
        raise ValueError(PRESSURE_MSG)
    need_challenge = trust_engine.effective_score(s) < NEED
    with LOCK:
        t = {"id": secrets.token_urlsafe(18), "amount": amount, "recipient": recipient,
             "expires": time.time() + TTL, "challenge_required": need_challenge,
             "needs_approval": amount >= SECOND_APPROVAL_OVER, "approved": False}
        s["pending_transfer"] = t          # one pending transfer at a time
        return public(t)


def can_execute(s, tid):
    t = s.get("pending_transfer")
    sid = s["session_id"]
    if not t or t["id"] != tid:
        return False, "Unknown or already used transaction."
    if time.time() > t["expires"]:
        s.pop("pending_transfer", None)
        return False, "Approval expired. Start the transfer again."
    if t["needs_approval"] and not t["approved"]:
        return False, "Amounts of %d or more need approval from a bank admin." % SECOND_APPROVAL_OVER
    if s["status"] != "VERIFIED":
        return False, "Session is %s." % s["status"].lower()
    if not callguard.is_checked(sid):
        return False, "Call Guard has not checked this call yet."
    if s.get("pressure_cap", 100) < NEED:
        return False, PRESSURE_MSG
    if t["challenge_required"] and not challenge.is_passed(tid, sid):
        return False, "Say the challenge sentence first."
    score = trust_engine.effective_score(s)
    if score < NEED:
        return False, "Trust %d is below %d." % (score, NEED)
    return True, "ok"


def approve(s, tid, approver_role):
    with LOCK:
        t = s.get("pending_transfer")
        if not t or t["id"] != tid:
            raise ValueError("Unknown or already used transaction.")
        if time.time() > t["expires"]:
            raise ValueError("Approval expired. Start the transfer again.")
        if approver_role != "admin":
            raise ValueError("Only a bank admin can approve this.")
        t["approved"] = True
        return public(t)


def execute(s, tid):
    with LOCK:
        ok, why = can_execute(s, tid)
        if not ok:
            raise ValueError(why)
        t = s.pop("pending_transfer")      # single use
        db_transfer(t["id"], s["speaker_id"], t["amount"], t["recipient"])
        return {"status": "Transfer executed (mock)", "amount": t["amount"],
                "recipient": t["recipient"]}