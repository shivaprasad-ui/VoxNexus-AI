import os
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ["VOX_DB"] = os.path.join(TMP, "t.sqlite3")

import io
import math
import struct
import wave

import database
database.DB = Path(os.environ["VOX_DB"])     # legacy tables also go to the temp database

import detectif
import speech_gate

MODE = {"fake": False, "match": True}
CALLS = {"enroll": []}


def fake_detect(audio):
    f = MODE["fake"]
    return {"result": {"label": "synthetic" if f else "real", "is_synthetic": f, "score": 0.99 if f else 0.01,
                       "threshold": 0.62, "verdict": "synthetic" if f else "real", "segments": [], "duration": 5}}


def fake_verify(speaker_id, audio):
    m = MODE["match"]
    return {"result": {"decision": "match" if m else "no_match", "similarity": 0.9 if m else 0.1, "threshold": 0.53}}


def fake_enroll(speaker_id, audio):
    CALLS["enroll"].append(speaker_id)
    return {"enrolled": True}


detectif.detect, detectif.verify, detectif.enroll = fake_detect, fake_verify, fake_enroll
speech_gate.has_speech = lambda data: True


def make_wav(seconds, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                               for i in range(int(seconds * rate))))
    return buf.getvalue()


from fastapi.testclient import TestClient

import auth
import customer
import main
import schema

auth.create_user("admin1", "AdminPass99", "admin", "Admin")
auth.create_user("cust1", "CustPass99", "customer", "Cust One", speaker_id="teamate1", balance=250000)
auth.create_user("cust2", "CustPass88", "customer", "Cust Two", speaker_id="teamate2", balance=500)


def client():
    return TestClient(main.app)


def login(c, u, p):
    r = c.post("/auth/login", data={"username": u, "password": p})
    assert r.status_code == 200, r.text


def rows(sql, args=()):
    c = schema.connect()
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


anon, c1, c2, adm = client(), client(), client(), client()

# 1. anonymous access is refused everywhere
for p in ("/api/customer/dashboard", "/api/customer/history", "/api/admin/enrollments", "/api/admin/audit"):
    assert anon.get(p).status_code == 401, p
assert anon.post("/api/customer/session/start").status_code == 401

# 2. the old open routes are gone
assert anon.post("/session/start", data={"speaker_id": "x", "role": "admin"}).status_code in (404, 405)
assert anon.post("/enroll").status_code in (404, 405)
assert anon.get("/audit").status_code == 404
assert anon.post("/txn/approve").status_code in (404, 405)
assert anon.post("/protect", data={"sid": "S-1", "action": "transfer_money"}).status_code in (401, 503)
assert anon.get("/ui", follow_redirects=False).status_code in (303, 307)

# 3. pages are only served to the right role
login(c1, "cust1", "CustPass99"); login(c2, "cust2", "CustPass88"); login(adm, "admin1", "AdminPass99")
assert anon.get("/customer", follow_redirects=False).status_code == 303
assert c1.get("/customer").status_code == 200
assert c1.get("/admin", follow_redirects=False).status_code == 303
assert adm.get("/admin").status_code == 200

# 4. a customer cannot use admin APIs
assert c1.get("/api/admin/enrollments").status_code in (401, 403)

# 5. no session before the voice enrollment is confirmed
assert c1.post("/api/customer/session/start").status_code == 403

# 6. enrollment goes to an admin queue; nothing reaches Eidos until approved
assert c2.post("/api/customer/enroll", files={"file": ("e.wav", make_wav(5), "audio/wav")}).status_code == 400
r = c1.post("/api/customer/enroll", files={"file": ("e.wav", make_wav(16), "audio/wav")})
assert r.status_code == 200 and r.json()["status"] == "PENDING", r.text
assert c1.post("/api/customer/enroll", files={"file": ("e.wav", make_wav(16), "audio/wav")}).status_code == 409
assert CALLS["enroll"] == []
pend = adm.get("/api/admin/enrollments").json()
assert len(pend) == 1 and pend[0]["customer_id"].startswith("C-")
eid = pend[0]["id"]
assert adm.get("/api/admin/enrollments/%d/audio" % eid).status_code == 200
assert c1.get("/api/admin/enrollments/%d/audio" % eid).status_code in (401, 403)
assert adm.post("/api/admin/enrollments/%d/decide" % eid, data={"decision": "REJECTED"}).status_code == 400
assert adm.post("/api/admin/enrollments/%d/decide" % eid, data={"decision": "APPROVED", "reason": "ok"}).status_code == 200
assert CALLS["enroll"] == ["teamate1"]
assert not os.path.exists(os.path.join(customer.PENDING_DIR, "%d.wav" % eid))
assert adm.post("/api/admin/enrollments/%d/decide" % eid, data={"decision": "APPROVED"}).status_code == 409
assert c1.get("/api/customer/dashboard").json()["enrollment"]["status"] == "APPROVED"

# 7. session starts; the server owns role and speaker; it is mirrored to the database
s = c1.post("/api/customer/session/start", data={"role": "admin", "speaker_id": "someone_else"}).json()
sid = s["session_id"]
assert s["status"] == "UNVERIFIED"
import session_manager
assert session_manager.get(sid)["role"] == "customer" and session_manager.get(sid)["speaker_id"] == "teamate1"
assert len(rows("SELECT * FROM sessions WHERE id = ?", (sid,))) == 1

# 8. another customer cannot touch this session or its transactions
w = make_wav(5)
assert c2.get("/api/customer/session/" + sid).status_code == 403
assert c2.post("/api/customer/session/%s/check" % sid, files={"file": ("a.wav", w, "audio/wav")}).status_code == 403
assert c2.post("/api/customer/callguard", data={"text": "hello there friend", "sid": sid}).status_code == 403
assert c2.post("/api/customer/txn/prepare", data={"sid": sid, "amount": 100, "recipient": "X"}).status_code == 403
assert c2.post("/api/customer/txn/confirm", data={"sid": sid, "txn_id": "x"}).status_code == 403
assert len(rows("SELECT * FROM security_events WHERE event_type = 'ACCESS_DENIED'")) >= 4

# 9. AI-generated voice suspends the session
MODE["fake"] = True
sf = c1.post("/api/customer/session/start").json()["session_id"]
j = c1.post("/api/customer/session/%s/check" % sf, data={"mode": "full"}, files={"file": ("a.wav", w, "audio/wav")}).json()
assert j["status"] == "SUSPENDED", j
assert len(rows("SELECT * FROM security_events WHERE event_type = 'FAKE_VOICE' AND session_id = ?", (sf,))) == 1
assert c1.post("/api/customer/session/%s/check" % sf, data={"mode": "monitor"}, files={"file": ("a.wav", w, "audio/wav")}).status_code == 403
assert len(rows("SELECT * FROM security_events WHERE event_type LIKE 'ENGINE_%'")) > 0
MODE["fake"] = False

# 10. different speaker: identity check fails
MODE["match"] = False
sm = c1.post("/api/customer/session/start").json()["session_id"]
j = c1.post("/api/customer/session/%s/check" % sm, data={"mode": "full"}, files={"file": ("a.wav", w, "audio/wav")}).json()
assert j["status"] != "VERIFIED", j
assert len(rows("SELECT * FROM security_events WHERE event_type = 'SPEAKER_MISMATCH' AND session_id = ?", (sm,))) == 1
MODE["match"] = True

# 11. normal flow: verify, Call Guard must run before a transfer can complete
sid = c1.post("/api/customer/session/start").json()["session_id"]
j = c1.post("/api/customer/session/%s/check" % sid, data={"mode": "full"}, files={"file": ("a.wav", w, "audio/wav")}).json()
assert j["status"] == "VERIFIED" and j["trust"] >= 90 and j["eidos"]["match"] is True, j
t = c1.post("/api/customer/txn/prepare", data={"sid": sid, "amount": 5000, "recipient": "Ravi"})
assert t.status_code == 200, t.text
txn = t.json()["txn"]["id"]
assert c1.post("/api/customer/txn/confirm", data={"sid": sid, "txn_id": txn}).status_code == 403   # Call Guard has not listened
cg = c1.post("/api/customer/callguard", data={"text": "Hello I would like to check my account balance please", "sid": sid})
assert cg.status_code == 200, cg.text
ok = c1.post("/api/customer/txn/confirm", data={"sid": sid, "txn_id": txn})
assert ok.status_code == 200 and ok.json()["balance"] == 245000, ok.text
assert c1.post("/api/customer/txn/confirm", data={"sid": sid, "txn_id": txn}).status_code == 403  # single use
assert rows("SELECT status FROM transactions WHERE id = ?", (txn,))[0]["status"] == "COMPLETED"
assert rows("SELECT balance FROM accounts WHERE customer_id = (SELECT id FROM users WHERE username='cust1')")[0]["balance"] == 245000

# 12. balance limit, and large amounts need admin approval (not available to customers)
assert c1.post("/api/customer/txn/prepare", data={"sid": sid, "amount": 999999999, "recipient": "X"}).status_code == 400
big = c1.post("/api/customer/txn/prepare", data={"sid": sid, "amount": 60000, "recipient": "Ravi"}).json()["txn"]
r = c1.post("/api/customer/txn/confirm", data={"sid": sid, "txn_id": big["id"]})
assert r.status_code == 403 and "approval" in r.text.lower(), r.text

# 13. pressure words block transfers
c1.post("/api/customer/callguard", data={"text": "Please send me the OTP right now", "sid": sid})
assert c1.post("/api/customer/txn/prepare", data={"sid": sid, "amount": 100, "recipient": "Ravi"}).status_code == 400
assert len(rows("SELECT * FROM security_events WHERE event_type = 'SCAM_SIGNAL' AND session_id = ?", (sid,))) >= 1

# 14. logout
assert c1.post("/auth/logout", data={"portal": "customer"}).status_code == 200
assert c1.get("/api/customer/dashboard").status_code == 401

print("all portal tests passed")
