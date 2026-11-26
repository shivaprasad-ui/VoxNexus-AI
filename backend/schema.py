"""Database schema and safe migration.
Additive only: existing tables (incidents, transfers) are never dropped or altered."""
import os
import shutil
import sqlite3
import time

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "security.sqlite3")
SCHEMA_VERSION = 1


def db_path():
    return os.environ.get("VOX_DB", DEFAULT_DB)


def connect():
    c = sqlite3.connect(db_path(), timeout=10, isolation_level=None)  # autocommit; use BEGIN where needed
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c


DDL_V1 = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('customer','admin')),
  full_name TEXT NOT NULL,
  speaker_id TEXT UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until REAL NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL UNIQUE REFERENCES users(id),
  balance INTEGER NOT NULL CHECK (balance >= 0),
  currency TEXT NOT NULL DEFAULT 'INR',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  last_seen REAL NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES users(id),
  started_at REAL NOT NULL,
  ended_at REAL,
  status TEXT NOT NULL,
  trust_score INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES users(id),
  session_id TEXT NOT NULL REFERENCES sessions(id),
  amount INTEGER NOT NULL CHECK (amount > 0),
  recipient TEXT NOT NULL,
  status TEXT NOT NULL,
  challenge_required INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  executed_at REAL
);
CREATE TABLE IF NOT EXISTS transaction_approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  txn_id TEXT NOT NULL REFERENCES transactions(id),
  admin_id TEXT NOT NULL REFERENCES users(id),
  decision TEXT NOT NULL CHECK (decision IN ('APPROVED','REJECTED')),
  reason TEXT NOT NULL,
  amount INTEGER NOT NULL,
  recipient TEXT NOT NULL,
  decided_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS security_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  customer_id TEXT,
  session_id TEXT,
  txn_id TEXT,
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',
  detail TEXT
);
CREATE TABLE IF NOT EXISTS voice_enrollments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id TEXT NOT NULL REFERENCES users(id),
  speaker_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  created_at REAL NOT NULL,
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at REAL
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON security_events(ts);
CREATE INDEX IF NOT EXISTS ix_events_customer ON security_events(customer_id);
CREATE INDEX IF NOT EXISTS ix_txn_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS ix_txn_status ON transactions(status);
CREATE INDEX IF NOT EXISTS ix_sessions_customer ON sessions(customer_id);
"""


def migrate():
    """Create missing tables. Backs up an existing database once, before the first migration."""
    p = db_path()
    existed = os.path.exists(p) and os.path.getsize(p) > 0
    c = connect()
    try:
        v = c.execute("PRAGMA user_version").fetchone()[0]
        if v >= SCHEMA_VERSION:
            return v
        if existed and v == 0:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            shutil.copy2(p, p + ".bak")
        c.executescript(DDL_V1)
        c.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        return SCHEMA_VERSION
    finally:
        c.close()


def log_event(event_type, customer_id=None, session_id=None, txn_id=None, severity="info", detail=""):
    c = connect()
    try:
        c.execute(
            "INSERT INTO security_events (ts, customer_id, session_id, txn_id, event_type, severity, detail) "
            "VALUES (?,?,?,?,?,?,?)",
            (time.time(), customer_id, session_id, txn_id, event_type, severity, str(detail)[:500]),
        )
    finally:
        c.close()