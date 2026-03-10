"""SQLite database operations."""

import json
import logging
import os
from datetime import datetime, timezone

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("CS_AGENT_DB_PATH",
                          "/home/user/workspace/mira-cs-agent-v2/data/cs_agent.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_emails (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    message_id TEXT UNIQUE,
    from_email TEXT,
    from_name TEXT,
    subject TEXT,
    received_at TEXT,
    body TEXT,
    category TEXT,
    status TEXT DEFAULT 'pending',
    shopify_order_id TEXT,
    shopify_order_number TEXT,
    shopify_data TEXT,
    draft_text TEXT,
    draft_gmail_id TEXT,
    rules_applied TEXT,
    thread_context TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    customer_email TEXT,
    customer_name TEXT,
    order_number TEXT,
    status TEXT NOT NULL,
    details TEXT,
    email_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processing_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT DEFAULT (datetime('now')),
    emails_found INTEGER DEFAULT 0,
    emails_processed INTEGER DEFAULT 0,
    drafts_created INTEGER DEFAULT 0,
    tasks_created INTEGER DEFAULT 0,
    errors TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "auto_processing": "true",
    "processing_interval_minutes": "10",
}


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    """Initialize database schema and default settings."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        await db.commit()
    finally:
        await db.close()


async def is_email_processed(message_id: str) -> bool:
    """Check if an email has already been processed."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)
        )
        row = await cursor.fetchone()
        return row is not None
    finally:
        await db.close()


async def save_processed_email(data: dict):
    """Save a processed email to the database."""
    db = await get_db()
    try:
        await db.execute("""
            INSERT OR REPLACE INTO processed_emails
            (id, thread_id, message_id, from_email, from_name, subject,
             received_at, body, category, status, shopify_order_id,
             shopify_order_number, shopify_data, draft_text, draft_gmail_id,
             rules_applied, thread_context, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            data.get("id", data.get("message_id", "")),
            data.get("thread_id"),
            data.get("message_id"),
            data.get("from_email"),
            data.get("from_name"),
            data.get("subject"),
            data.get("received_at"),
            data.get("body"),
            data.get("category"),
            data.get("status", "pending"),
            data.get("shopify_order_id"),
            data.get("shopify_order_number"),
            json.dumps(data.get("shopify_data")) if data.get("shopify_data") else None,
            data.get("draft_text"),
            data.get("draft_gmail_id"),
            json.dumps(data.get("rules_applied")) if data.get("rules_applied") else None,
            json.dumps(data.get("thread_context")) if data.get("thread_context") else None,
        ))
        await db.commit()
    finally:
        await db.close()


async def get_emails(status: str | None = None, limit: int = 50,
                     offset: int = 0) -> list[dict]:
    """Get processed emails from the database."""
    db = await get_db()
    try:
        if status:
            cursor = await db.execute(
                "SELECT * FROM processed_emails WHERE status = ? ORDER BY received_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM processed_emails ORDER BY received_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_email_by_id(email_id: str) -> dict | None:
    """Get a single email by ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM processed_emails WHERE id = ?", (email_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_email_status(email_id: str, status: str):
    """Update email status."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE processed_emails SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, email_id)
        )
        await db.commit()
    finally:
        await db.close()


async def update_email_draft(email_id: str, draft_text: str,
                              draft_gmail_id: str | None = None):
    """Update the draft text for an email."""
    db = await get_db()
    try:
        if draft_gmail_id:
            await db.execute(
                "UPDATE processed_emails SET draft_text = ?, draft_gmail_id = ?, status = 'draft_created', updated_at = datetime('now') WHERE id = ?",
                (draft_text, draft_gmail_id, email_id)
            )
        else:
            await db.execute(
                "UPDATE processed_emails SET draft_text = ?, updated_at = datetime('now') WHERE id = ?",
                (draft_text, email_id)
            )
        await db.commit()
    finally:
        await db.close()


# --- Tasks ---

async def create_task(data: dict) -> int:
    """Create a new task and return its ID."""
    db = await get_db()
    try:
        cursor = await db.execute("""
            INSERT INTO tasks (type, customer_email, customer_name, order_number,
                              status, details, email_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data["type"],
            data.get("customer_email"),
            data.get("customer_name"),
            data.get("order_number"),
            data["status"],
            json.dumps(data.get("details", {})),
            data.get("email_id"),
        ))
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_tasks(task_type: str | None = None, limit: int = 50) -> list[dict]:
    """Get tasks, optionally filtered by type."""
    db = await get_db()
    try:
        if task_type:
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE type = ? ORDER BY updated_at DESC LIMIT ?",
                (task_type, limit)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_task_by_id(task_id: int) -> dict | None:
    """Get a single task by ID."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_task(task_id: int, updates: dict):
    """Update a task."""
    db = await get_db()
    try:
        set_clauses = []
        values = []
        for key in ["status", "details", "customer_email", "customer_name", "order_number"]:
            if key in updates:
                set_clauses.append(f"{key} = ?")
                val = updates[key]
                if key == "details" and isinstance(val, dict):
                    val = json.dumps(val)
                values.append(val)
        if not set_clauses:
            return
        set_clauses.append("updated_at = datetime('now')")
        values.append(task_id)
        await db.execute(
            f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?", values
        )
        await db.commit()
    finally:
        await db.close()


async def find_tasks_for_customer(email: str) -> list[dict]:
    """Find existing tasks for a customer."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE customer_email = ? ORDER BY updated_at DESC",
            (email,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# --- Processing Log ---

async def log_processing_run(data: dict):
    """Log a processing run."""
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO processing_log (emails_found, emails_processed,
                                        drafts_created, tasks_created,
                                        errors, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get("emails_found", 0),
            data.get("emails_processed", 0),
            data.get("drafts_created", 0),
            data.get("tasks_created", 0),
            json.dumps(data.get("errors", [])),
            data.get("duration_ms", 0),
        ))
        await db.commit()
    finally:
        await db.close()


async def get_processing_logs(limit: int = 20) -> list[dict]:
    """Get recent processing logs."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM processing_log ORDER BY run_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


# --- Settings ---

async def get_settings() -> dict:
    """Get all settings as a dict."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        await db.close()


async def update_setting(key: str, value: str):
    """Update a single setting."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()
    finally:
        await db.close()
