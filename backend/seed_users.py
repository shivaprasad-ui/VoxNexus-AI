"""Create local prototype accounts; passwords are entered interactively, never stored in source."""
import getpass

import schema
from auth import create_user


USERS = (
    ("admin1", "Admin", "admin", None, 0),
    ("cust1", "Cust One", "customer", "teamate1", 250000),
    ("cust2", "Cust Two", "customer", "teamate2", 500),
)


def _password(username):
    while True:
        password = getpass.getpass("Password for %s (minimum 8 characters): " % username)
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            continue
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords did not match.")
            continue
        return password


def main():
    schema.migrate()
    c = schema.connect()
    try:
        existing = {
            row["username"].lower()
            for row in c.execute("SELECT username FROM users")
        }
    finally:
        c.close()

    for username, full_name, role, speaker_id, balance in USERS:
        if username.lower() in existing:
            print("skip %s: already exists" % username)
            continue
        password = _password(username)
        create_user(username, password, role, full_name, speaker_id, balance)
        print("created %s (%s)" % (username, role))


if __name__ == "__main__":
    main()
