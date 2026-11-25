import sys
import time
import requests

BASE = "http://127.0.0.1:8001"


def send(sid, path):
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE}/session/{sid}/check",
            data={"mode": "monitor"},
            files={"file": (path, f, "audio/wav")},
        )
    try:
        body = r.json()
    except Exception:
        body = r.text
    print(path, "->", r.status_code, body)
    return r.status_code


sid = sys.argv[1]
for path in sys.argv[2:]:
    if send(sid, path) == 403:
        print("SESSION SUSPENDED - sentinel stopped")
        break
    time.sleep(1)