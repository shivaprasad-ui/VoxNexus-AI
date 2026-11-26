"""Usage: python mark_enrolled.py cust1 cust2
Marks demo customers whose voice was ALREADY enrolled in Eidos (with their consent) as APPROVED."""
import sys
import time

import schema

schema.migrate()
c = schema.connect()
admin = c.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1").fetchone()
if admin is None:
    sys.exit("No admin user found. Run seed_users.py first.")
for username in sys.argv[1:]:
    u = c.execute("SELECT id, speaker_id FROM users WHERE username = ? AND role = 'customer'",
                  (username,)).fetchone()
    if u is None or not u["speaker_id"]:
        print("skip %s: not a customer with a speaker id" % username)
        continue
    if c.execute("SELECT 1 FROM voice_enrollments WHERE customer_id = ? AND status = 'APPROVED'",
                 (u["id"],)).fetchone():
        print("skip %s: already approved" % username)
        continue
    now = time.time()
    c.execute("INSERT INTO voice_enrollments (customer_id, speaker_id, status, created_at, reviewed_by, reviewed_at) "
              "VALUES (?,?,?,?,?,?)", (u["id"], u["speaker_id"], "APPROVED", now, admin["id"], now))
    print("marked %s (%s) as enrolled" % (username, u["speaker_id"]))
c.close()
