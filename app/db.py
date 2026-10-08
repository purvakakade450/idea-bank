"""SQLite storage. One connection per request/thread; WAL mode so the web app
and the background worker can share the same file safely."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

_local = threading.local()
_path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT DEFAULT '',
  url TEXT NOT NULL UNIQUE,
  published_at TEXT,
  fetched_at TEXT NOT NULL,
  processed INTEGER NOT NULL DEFAULT 0,
  meta TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON signals(processed, fetched_at);

CREATE TABLE IF NOT EXISTS problems (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  statement TEXT NOT NULL,
  who TEXT DEFAULT '',
  why_now TEXT DEFAULT '',
  sector TEXT DEFAULT 'Other',
  fields TEXT DEFAULT '[]',
  evidence_count INTEGER NOT NULL DEFAULT 0,
  has_idea INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_signals (
  problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
  signal_id INTEGER NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
  PRIMARY KEY (problem_id, signal_id)
);

CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  problem_id INTEGER REFERENCES problems(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  sector TEXT DEFAULT 'Other',
  problem TEXT NOT NULL,
  solution TEXT DEFAULT '',
  product TEXT DEFAULT 'mix',
  budget TEXT DEFAULT 'mid',
  setting TEXT DEFAULT 'any',
  model TEXT DEFAULT '{}',
  roles TEXT DEFAULT '{}',
  hours INTEGER DEFAULT 30,
  months INTEGER DEFAULT 6,
  scores TEXT DEFAULT '{}',
  total INTEGER DEFAULT 0,
  checks TEXT DEFAULT '{}',
  gates TEXT DEFAULT '{}',
  domain_metrics TEXT DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
  origin TEXT NOT NULL DEFAULT 'engine',    -- seed | engine | user | team
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status, total);

CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT DEFAULT '',
  months INTEGER DEFAULT 6,
  interest TEXT DEFAULT 'Any',
  product TEXT DEFAULT 'mix',
  budget TEXT DEFAULT 'unsure',
  setting TEXT DEFAULT 'any',
  city TEXT DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name TEXT DEFAULT '',
  field TEXT NOT NULL,
  skills TEXT DEFAULT '',
  hours INTEGER NOT NULL DEFAULT 10,
  months INTEGER NOT NULL DEFAULT 6,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reviewers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  token_hash TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ok INTEGER NOT NULL,
  fetched INTEGER DEFAULT 0,
  added INTEGER DEFAULT 0,
  error TEXT DEFAULT ''
);
"""

JSON_COLS = {"fields", "roles", "scores", "checks", "gates", "domain_metrics", "meta", "model"}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init(path):
    global _path
    _path = path
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    c = conn()
    c.executescript(SCHEMA)
    have = {r["name"] for r in c.execute("PRAGMA table_info(ideas)")}
    for col, ddl in (("reviewed_by", "TEXT DEFAULT ''"), ("reviewed_at", "TEXT"), ("review_note", "TEXT DEFAULT ''")):
        if col not in have:
            c.execute(f"ALTER TABLE ideas ADD COLUMN {col} {ddl}")
    if "email" not in {r["name"] for r in c.execute("PRAGMA table_info(reviewers)")}:
        c.execute("ALTER TABLE reviewers ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    c.commit()


def conn():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(_path, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.c = c
    return c


def close():
    c = getattr(_local, "c", None)
    if c is not None:
        c.close()
        _local.c = None


def row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS & d.keys():
        try:
            d[k] = json.loads(d[k] or "null")
        except (TypeError, ValueError):
            d[k] = None
    return d


def q(sql, args=(), one=False):
    cur = conn().execute(sql, args)
    rows = [row(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    c = conn()
    cur = c.execute(sql, args)
    c.commit()
    return cur.lastrowid


def dumps(v):
    return json.dumps(v, ensure_ascii=False)
