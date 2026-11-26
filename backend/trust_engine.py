import time
from session_manager import log

IDENTITY_TTL = 300                  # seconds before identity trust expires
EXPIRED_CAP = 50                    # score cap after expiry
REQUIRED = {"check_balance": 40, "update_profile": 70, "transfer_money": 90,"access_records": 70,"reset_password": 90,"unlock_door": 90,}


def _suspend(s, why):
    s["trust_score"] = 0
    s["status"] = "SUSPENDED"
    log(s, "SUSPENDED", why)


def effective_score(s):
    """Apply expiry: old identity checks lose value."""
    if s["status"] == "VERIFIED" and s["last_identity_check"]:
        if time.time() - s["last_identity_check"] > IDENTITY_TTL:
            return min(s["trust_score"], EXPIRED_CAP)
    return s["trust_score"]


def update(s, fake, match, identity_checked):
    """fake / match are True, False or None (unknown)."""
    if s["status"] == "SUSPENDED":
        log(s, "IGNORED", "Session already suspended")
        return
    if fake is True:
        _suspend(s, "Voice flagged as AI-generated")
    elif identity_checked and match is False:
        s["identity_fails"] = s.get("identity_fails", 0) + 1
        if s["identity_fails"] >= 2 or s["status"] == "VERIFIED":
            _suspend(s, "Speaker does not match the registered person")
        else:
            log(s, "IDENTITY_RETRY", "Voice did not match. One more attempt allowed.")
    elif identity_checked and fake is False and match is True:
        s["trust_score"] = min(100, s.get("pressure_cap",100))
        s["status"] = "VERIFIED"
        s["verification_count"] += 1
        s["last_identity_check"] = time.time()
        log(s, "VERIFIED", "Real voice and identity match")
    elif fake is False and not identity_checked:
        log(s, "MONITOR_OK", "Voice still looks real (identity not re-checked)")
    else:
        s["trust_score"] = max(0, s["trust_score"] - 30)
        log(s, "UNCERTAIN", f"Unclear result, trust now {s['trust_score']}")


def authorize(s, action):
    """Returns (decision, reason). Decisions: ALLOW, STEP_UP, BLOCK."""
    if s["status"] == "SUSPENDED":
        return "BLOCK", "Session suspended. Contact the person on a trusted number."
    need = REQUIRED.get(action, 90)     # unknown actions count as sensitive
    score = effective_score(s)
    if action not in REQUIRED:
        return "BLOCK", "Unknown action"
    if s["status"] == "VERIFIED" and score >= need:
        return "ALLOW", f"Trust {score} meets the {need} needed for {action}."
    return "STEP_UP", f"Trust {score} is below the {need} needed for {action}. Run a full identity check."
