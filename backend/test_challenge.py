import challenge, callguard, transaction_guard as tg

tg.db_transfer = lambda *a: None      # keep the test off the real database

P = "The blue train arrives at seven near gate four."
assert challenge.matches("the blue train arrives at 7 near gate 4", P)[0], "digits"
assert challenge.matches("blue train arrives at seven near gate four", P)[0], "one missed word"
assert not challenge.matches("hello how are you today", P)[0], "wrong words"


def sess(trust, status="VERIFIED", sid="S-t", **extra):
    s = {"session_id": sid, "speaker_id": "x", "trust_score": trust, "status": status,
         "last_identity_check": None, "events": []}
    s.update(extra)
    return s


def refused(fn, *a):
    try:
        fn(*a)
    except ValueError as e:
        return str(e)
    return None


callguard.mark_checked("S-t", "one two three four")

# 1. high trust: no challenge, and it works only once
s = sess(100)
t = tg.prepare(s, 5000, "Ravi")
assert not t["challenge_required"]
assert not t["needs_approval"] and not t["approved"]
assert tg.execute(s, t["id"])["amount"] == 5000
assert refused(tg.execute, s, t["id"]), "must work only once"

# Large amounts require the simulated second approval; smaller ones do not.
s = sess(100, sid="S-admin")
callguard.mark_checked("S-admin", "one two three four")
t = tg.prepare(s, 60000, "Ravi")
assert t["needs_approval"] and not t["approved"]
assert "bank admin" in tg.can_execute(s, t["id"])[1]
assert "Only a bank admin" in refused(tg.approve, s, t["id"], "customer")
assert tg.approve(s, t["id"], "admin")["approved"]
assert tg.can_execute(s, t["id"])[0]

# 2. low trust: the challenge is required
s = sess(70, "UNCERTAIN")
t = tg.prepare(s, 9000, "Asha")
assert t["challenge_required"]
c = challenge.issue("S-t", t["id"])
assert not challenge.record_result("S-t", c["challenge_id"], "hello there", True)["passed"]
assert challenge.record_result("S-t", c["challenge_id"], c["phrase"], True)["passed"]
assert not tg.can_execute(s, t["id"])[0], "trust still low"
s["trust_score"], s["status"] = 100, "VERIFIED"      # what a passed full check does
assert tg.can_execute(s, t["id"])[0], "after challenge"

# 3. pressure heard: refused up front
assert "Call Guard" in (refused(tg.prepare, sess(85, pressure_cap=85), 100, "X") or "")

# 4. call never analysed
s = sess(100, sid="S-never")
t = tg.prepare(s, 100, "X")
assert "Call Guard" in tg.can_execute(s, t["id"])[1]

# 5. suspended, expired, bad input
assert refused(tg.prepare, sess(0, "SUSPENDED"), 100, "X")
s = sess(100)
t = tg.prepare(s, 100, "X")
s["pending_transfer"]["expires"] -= 1000
assert "expired" in tg.can_execute(s, t["id"])[1].lower()
assert refused(tg.prepare, sess(100), 0, "X")
assert refused(tg.prepare, sess(100), 100, "  ")
print("ALL CHALLENGE TESTS PASSED")