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
print("all trust tests passed")