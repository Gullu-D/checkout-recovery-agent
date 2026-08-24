"""SQLite-backed audit trail. Every decision the agent ever makes is
written here before any action is taken — the log is append-only and is
the single source of truth for the metrics report and the dashboard."""
import sqlite3
import os
from . import config
from .models import AuditRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkout_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    confidence REAL NOT NULL,
    action TEXT NOT NULL,
    rationale TEXT NOT NULL,
    guardrail_notes TEXT NOT NULL,
    action_success INTEGER NOT NULL,
    action_detail TEXT NOT NULL
);
"""


def get_connection():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def reset_db():
    """Wipe the audit log — used at the start of a fresh batch run so demo
    runs are reproducible. Never called implicitly by the API."""
    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS audit_log")
    conn.execute(_SCHEMA)
    conn.commit()
    conn.close()


def write_record(checkout_id, round_number, timestamp, root_cause, confidence,
                  action, rationale, guardrail_notes, action_success, action_detail):
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_log
           (checkout_id, round_number, timestamp, root_cause, confidence,
            action, rationale, guardrail_notes, action_success, action_detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (checkout_id, round_number, timestamp, root_cause, confidence,
         action, rationale, guardrail_notes, int(action_success), action_detail),
    )
    conn.commit()
    conn.close()


def fetch_all(limit: int = 500):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [AuditRecord(**dict(r)) for r in rows]


def fetch_for_checkout(checkout_id: str):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE checkout_id = ? ORDER BY id ASC", (checkout_id,)
    ).fetchall()
    conn.close()
    return [AuditRecord(**dict(r)) for r in rows]


def count_actions_for_checkout(checkout_id: str) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM audit_log WHERE checkout_id = ? "
        "AND action NOT IN ('NO_ACTION_COOLDOWN', 'NO_ACTION_LOW_CONFIDENCE')",
        (checkout_id,),
    ).fetchone()
    conn.close()
    return row["c"] if row else 0
