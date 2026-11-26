import session_manager as sm, trust_engine as te

s = sm.create("teamate1")
assert te.authorize(s, "transfer_money")[0] == "STEP_UP"       # new session gets no access
te.update(s, False, True, True)                                 # full check passes
assert te.authorize(s, "transfer_money")[0] == "ALLOW"
te.update(s, False, None, False)                                # monitor ok: trust holds
assert te.authorize(s, "transfer_money")[0] == "ALLOW"
te.update(s, True, None, False)                                 # fake detected mid-call
assert te.authorize(s, "check_balance")[0] == "BLOCK"           # even the lowest action is blocked
te.update(s, False, True, True)                                 # a later "good" check can't revive it
assert s["status"] == "SUSPENDED"

retry = sm.create("teamate1")
te.update(retry, False, False, True)
assert retry["status"] == "UNVERIFIED"
assert retry["identity_fails"] == 1
assert retry["events"][-1]["kind"] == "IDENTITY_RETRY"
te.update(retry, False, True, True)
assert retry["status"] == "VERIFIED"

second_failure = sm.create("teamate1")
te.update(second_failure, False, False, True)
te.update(second_failure, False, False, True)
assert second_failure["status"] == "SUSPENDED"

verified_mismatch = sm.create("teamate1")
te.update(verified_mismatch, False, True, True)
te.update(verified_mismatch, False, False, True)
assert verified_mismatch["status"] == "SUSPENDED"
print("all trust tests passed")