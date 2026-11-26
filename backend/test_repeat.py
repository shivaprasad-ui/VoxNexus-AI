import callguard
from callguard import analyze

s = {"status": "VERIFIED", "trust_score": 100, "events": []}
for n in (5, 10, 15, 25):
    r = analyze(" ".join(["Hello."] * n))
    out = callguard.apply_penalty("T", s, r["heard"], r["repeat_units"])
    print(n, "hellos -> units", r["repeat_units"], "| lost", out["penalty"], "| trust", s["trust_score"])