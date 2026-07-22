#!/usr/bin/env python3
"""SQLite Outbox Queue for Plant IoT Sensor Telemetry.

Provides local persistent queuing (Outbox pattern) to prevent data loss when
network or Supabase API issues occur.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_DB_PATH = Path(__file__).parent / "data.db"


def get_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    env_path = os.getenv("OUTBOX_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_outbox(db_path: Path | str | None = None) -> None:
    """Initialize the outbox table in SQLite."""
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                synced_at TIMESTAMP,
                last_error TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox_queue(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbox_created ON outbox_queue(created_at)"
        )


def enqueue(payload: dict[str, Any], db_path: Path | str | None = None) -> int:
    """Enqueue a payload into outbox_queue with status 'pending'."""
    init_outbox(db_path)
    device_id = payload.get("device_id", "unknown")
    if "created_at" not in payload:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()

    payload_json = json.dumps(payload, ensure_ascii=False)
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO outbox_queue (device_id, payload, status)
               VALUES (?, ?, 'pending')""",
            (device_id, payload_json),
        )
        return cursor.lastrowid


def get_pending(limit: int = 50, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Retrieve pending outbox items sorted by id."""
    init_outbox(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT id, device_id, payload, status, retry_count, created_at
               FROM outbox_queue
               WHERE status IN ('pending', 'failed')
               ORDER BY id ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    results = []
    for row in rows:
        try:
            item_payload = json.loads(row["payload"])
        except Exception:
            item_payload = {}
        results.append({
            "id": row["id"],
            "device_id": row["device_id"],
            "payload": item_payload,
            "status": row["status"],
            "retry_count": row["retry_count"],
            "created_at": row["created_at"],
        })
    return results


def mark_synced(record_ids: list[int] | int, db_path: Path | str | None = None) -> None:
    """Mark record(s) as synced in outbox_queue."""
    if isinstance(record_ids, int):
        record_ids = [record_ids]
    if not record_ids:
        return
    init_outbox(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" for _ in record_ids)
    with get_connection(db_path) as conn:
        conn.execute(
            f"""UPDATE outbox_queue
                SET status = 'synced', synced_at = ?
                WHERE id IN ({placeholders})""",
            [now_iso] + list(record_ids),
        )


def mark_failed(record_id: int, error_msg: str, db_path: Path | str | None = None) -> None:
    """Update record status to 'failed' and record error message."""
    init_outbox(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE outbox_queue
                SET status = 'failed', retry_count = retry_count + 1, last_error = ?
                WHERE id = ?""",
            (str(error_msg)[:500], record_id),
        )


def count_pending(db_path: Path | str | None = None) -> int:
    """Count remaining unsynced outbox records."""
    init_outbox(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM outbox_queue WHERE status IN ('pending', 'failed')"
        ).fetchone()
        return row[0] if row else 0


def flush_outbox(
    send_fn: Callable[[dict[str, Any]], bool],
    limit: int = 50,
    db_path: Path | str | None = None,
) -> tuple[int, int]:
    """Attempt to resend pending records using send_fn.

    Returns tuple (synced_count, failed_count).
    """
    items = get_pending(limit=limit, db_path=db_path)
    if not items:
        return 0, 0

    synced_count = 0
    failed_count = 0

    for item in items:
        rec_id = item["id"]
        payload = item["payload"]
        try:
            success = send_fn(payload)
            if success:
                mark_synced(rec_id, db_path=db_path)
                synced_count += 1
            else:
                mark_failed(rec_id, "send_fn returned False", db_path=db_path)
                failed_count += 1
        except Exception as exc:
            mark_failed(rec_id, str(exc), db_path=db_path)
            failed_count += 1

    return synced_count, failed_count
