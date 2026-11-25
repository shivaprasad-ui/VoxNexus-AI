import json
import time
from pathlib import Path

FILE = Path("audit_log.jsonl")


def log(sid, event, **details):
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "sid": sid, "event": event, **details}
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read(sid=None, limit=50):
    if not FILE.exists():
        return []
    rows = [json.loads(line) for line in FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if sid:
        rows = [r for r in rows if r["sid"] == sid]
    return rows[-limit:]