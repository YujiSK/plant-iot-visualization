#!/usr/bin/env python3
"""Lightweight Supabase REST health check for Plant IoT."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


def _masked_key_label(key: str) -> str:
    if not key:
        return "unset"
    return f"set len={len(key)} prefix={key[:8]} suffix={key[-4:]}"


def health_check(http_client=requests) -> dict[str, Any]:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY", "")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is not set")

    endpoint = (
        f"{supabase_url}/rest/v1/sensor_logs"
        "?select=id,created_at&order=created_at.desc&limit=1"
    )
    response = http_client.get(
        endpoint,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        timeout=10,
    )
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_code": response.status_code,
        "ok": response.ok,
        "key": _masked_key_label(supabase_key),
    }
    if response.ok:
        rows = response.json()
        result["latest_sensor_log"] = rows[0] if isinstance(rows, list) and rows else None
    else:
        result["body"] = response.text[:500]
    response.raise_for_status()
    return result


def main() -> int:
    result = health_check()
    latest = result.get("latest_sensor_log") or {}
    print(
        "supabase health ok: "
        f"status={result['status_code']} "
        f"latest_sensor_log_id={latest.get('id')} "
        f"latest_sensor_log_created_at={latest.get('created_at')} "
        f"key={result['key']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
