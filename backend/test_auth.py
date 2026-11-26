import os
import tempfile
import time

os.environ["VOX_DB"] = os.path.join(tempfile.mkdtemp(), "test.sqlite3")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import auth
import schema

schema.migrate()
auth.create_user("admin1", "AdminPass99", "admin", "Admin")
auth.create_user("cust1", "CustPass99", "customer", "Cust One", speaker_id="teamate1", balance=1000)
auth.create_user("cust2", "CustPass88", "customer", "Cust Two", speaker_id="teamate2", balance=500)

app = FastAPI()
app.include_router(auth.router)


@app.get("/t/customer")
def t_customer(u=Depends(auth.require_customer)):
    return {"u": u["username"]}


@app.get("/t/admin")
def t_admin(u=Depends(auth.require_admin)):
    return {"u": u["username"]}


def login(client, user, pw, **extra):
    data = {"username": user, "password": pw}
    data.update(extra)
    return client.post("/auth/login", data=data)


def cookie_header(name, value):
    return {"Cookie": "%s=%s" % (name, value)}


def db(sql, args=()):
    c = schema.connect()
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


# 1. no cookie -> 401
assert TestClient(app).get("/t/customer").status_code == 401

# 2. customer login; the role comes from the database even if the client sends role=admin
c = TestClient(app)
r = login(c, "cust1", "CustPass99", role="admin")
assert r.status_code == 200 and r.json()["role"] == "customer", r.text
assert c.get("/t/customer").status_code == 200
assert c.get("/t/admin").status_code == 401  # no admin cookie

# 3. a customer token placed in the admin cookie is refused
tok = r.cookies.get("vx_customer")
assert tok
r2 = TestClient(app).get("/t/admin", headers=cookie_header("vx_admin", tok))
assert r2.status_code == 403, r2.status_code

# 4. admin login works and cannot use customer routes
a = TestClient(app)
ra = login(a, "admin1", "AdminPass99")
assert ra.json()["role"] == "admin"
assert a.get("/t/admin").status_code == 200
assert a.get("/t/customer").status_code == 401

# 5. wrong password and unknown user give the same message
w1 = login(TestClient(app), "cust1", "wrong-password")
w2 = login(TestClient(app), "nobody", "wrong-password")
assert w1.status_code == w2.status_code == 401
assert w1.json()["detail"] == w2.json()["detail"]

# 6. lockout after 5 wrong attempts, even with the correct password afterwards
lk = TestClient(app)
for _ in range(5):
    assert login(lk, "cust2", "bad-password-1").status_code == 401
assert login(lk, "cust2", "CustPass88").status_code == 429

# 7. logout revokes the token
c2 = TestClient(app)
r3 = login(c2, "cust1", "CustPass99")
t3 = r3.cookies.get("vx_customer")
assert c2.post("/auth/logout", data={"portal": "customer"}).status_code == 200
assert TestClient(app).get("/t/customer", headers=cookie_header("vx_customer", t3)).status_code == 401

# 8. absolute expiry
c3 = TestClient(app)
t4 = login(c3, "cust1", "CustPass99").cookies.get("vx_customer")
h = auth._hash_token(t4)
c = schema.connect()
c.execute("UPDATE login_sessions SET expires_at = 1 WHERE token_hash = ?", (h,))
c.close()
assert TestClient(app).get("/t/customer", headers=cookie_header("vx_customer", t4)).status_code == 401

# 9. idle expiry
t5 = login(TestClient(app), "cust1", "CustPass99").cookies.get("vx_customer")
c = schema.connect()
c.execute("UPDATE login_sessions SET last_seen = ? WHERE token_hash = ?",
          (time.time() - auth.IDLE_TTL - 5, auth._hash_token(t5)))
c.close()
assert TestClient(app).get("/t/customer", headers=cookie_header("vx_customer", t5)).status_code == 401

# 10. passwords are stored as Argon2 hashes, never in readable form
row = db("SELECT password_hash FROM users WHERE username = 'cust1'")[0]
assert row["password_hash"].startswith("$argon2") and "CustPass99" not in row["password_hash"]

# 11. a deactivated user is locked out immediately
t6 = login(TestClient(app), "cust1", "CustPass99").cookies.get("vx_customer")
c = schema.connect()
c.execute("UPDATE users SET active = 0 WHERE username = 'cust1'")
c.close()
assert TestClient(app).get("/t/customer", headers=cookie_header("vx_customer", t6)).status_code == 401
c = schema.connect()
c.execute("UPDATE users SET active = 1 WHERE username = 'cust1'")
c.close()

# 12. input validation
for bad in (lambda: auth.create_user("x1", "short", "customer", "X"),
            lambda: auth.create_user("x2", "LongEnough1", "superuser", "X"),
            lambda: auth.create_user("cust1", "LongEnough1", "customer", "Dup")):
    try:
        bad()
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

# 13. each customer gets exactly one account
assert db("SELECT COUNT(*) AS n FROM accounts")[0]["n"] == 2
# 14. security events were recorded
assert db("SELECT COUNT(*) AS n FROM security_events WHERE event_type = 'LOGIN_LOCKED'")[0]["n"] == 1

print("all auth tests passed")