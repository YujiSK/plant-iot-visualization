#!/usr/bin/env python3
"""Unified Alert Manager for Plant IoT Transmission & Heartbeat Monitoring.

Handles stateful error tracking, 3-consecutive-failure thresholds, anti-spam
cooldowns, dual notifications (Slack + LINE), and recovery alerts.
"""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from slack_notifier import send_line_message, send_slack_message

DEFAULT_ALERT_STATE_PATH = Path(__file__).parent / "alert_state.json"
DEFAULT_STATE = {
    "transmission": {
        "consecutive_failures": 0,
        "first_failure_at": None,
        "last_success_at": None,
        "alert_active": False,
        "last_alert_at": None,
        "last_error_summary": None,
    },
    "heartbeat": {
        "warning_active": False,
        "critical_active": False,
        "last_alert_at": None,
    },
    "system": {
        "alert_active": False,
        "last_alert_at": None,
    },
}

FAILURE_THRESHOLD = 3
RENOTIFY_COOLDOWN_SECONDS = 3600  # Renotify every 1 hour if error persists


def current_jst_string() -> str:
    """Return formatted current time in JST."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M JST")


def get_state_path(state_path: Path | str | None = None) -> Path:
    if state_path:
        return Path(state_path)
    env_path = os.getenv("ALERT_STATE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_ALERT_STATE_PATH


def load_alert_state(state_path: Path | str | None = None) -> dict[str, Any]:
    path = get_state_path(state_path)
    state = deepcopy(DEFAULT_STATE)
    if not path.exists():
        return state
    try:
        with path.open(encoding="utf-8") as f:
            saved = json.load(f)
            if isinstance(saved, dict):
                for key in ("transmission", "heartbeat", "system"):
                    if key in saved and isinstance(saved[key], dict):
                        state[key].update(saved[key])
    except Exception as exc:
        print(f"[alert_manager] failed to load state: {exc}", file=sys.stderr)
    return state


def save_alert_state(state: dict[str, Any], state_path: Path | str | None = None) -> None:
    path = get_state_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    except Exception as exc:
        print(f"[alert_manager] failed to save state: {exc}", file=sys.stderr)


def recommend_action(error_summary: str) -> str:
    err_lower = error_summary.lower()
    if "401" in err_lower or "invalid api key" in err_lower or "unauthorized" in err_lower:
        return "Check SUPABASE_SENSOR_KEY / SUPABASE_KEY in .env"
    if "403" in err_lower or "forbidden" in err_lower:
        return "Check Supabase Row Level Security (RLS) policies or API key permissions"
    if "500" in err_lower or "502" in err_lower or "503" in err_lower or "504" in err_lower:
        return "Supabase service error or maintenance. Standby for auto-recovery"
    if "timeout" in err_lower:
        return "Check network latency or Supabase response times"
    if "connection" in err_lower or "nameresolution" in err_lower or "dns" in err_lower:
        return "Check Wi-Fi / LAN connection or DNS configuration"
    if "ssl" in err_lower or "certificate" in err_lower:
        return "Check system clock / SSL certificate validity"
    return "Check system logs and network configuration"


def broadcast_message(
    message: str,
    webhook_url: str | None = None,
    line_channel_access_token: str | None = None,
    line_to_id: str | None = None,
    post=requests.post,
) -> bool:
    """Send message to BOTH Slack and LINE."""
    slack_ok = send_slack_message(message, webhook_url=webhook_url, post=post)
    line_ok = send_line_message(
        message,
        channel_access_token=line_channel_access_token,
        to_id=line_to_id,
        post=post,
    )
    return slack_ok or line_ok


def record_transmission_failure(
    device_id: str,
    error_summary: str,
    state_path: Path | str | None = None,
    webhook_url: str | None = None,
    line_token: str | None = None,
    line_to: str | None = None,
    post=requests.post,
) -> bool:
    """Record a transmission failure, update count, and send dual alerts if threshold met."""
    state = load_alert_state(state_path)
    tx = state["transmission"]

    tx["consecutive_failures"] += 1
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = datetime.now(timezone.utc).timestamp()
    if not tx["first_failure_at"]:
        tx["first_failure_at"] = now_iso
    tx["last_error_summary"] = error_summary

    alert_sent = False
    count = tx["consecutive_failures"]
    last_alert_ts = tx.get("last_alert_ts", 0)

    # Check if threshold reached (3 consecutive failures)
    if count >= FAILURE_THRESHOLD:
        should_alert = not tx["alert_active"] or (now_ts - last_alert_ts >= RENOTIFY_COOLDOWN_SECONDS)
        if should_alert:
            action = recommend_action(error_summary)
            last_success = tx["last_success_at"] or "Unknown"

            msg = (
                "🚨 Plant IoT Alert\n\n"
                "Supabaseへの送信に失敗しています。\n\n"
                f"{error_summary}\n\n"
                f"Device:\n{device_id}\n\n"
                f"Failure count:\n{count}\n\n"
                f"Last successful upload:\n{last_success}\n\n"
                f"Action recommended:\n{action}"
            )
            broadcast_message(
                msg,
                webhook_url=webhook_url,
                line_channel_access_token=line_token,
                line_to_id=line_to,
                post=post,
            )
            tx["alert_active"] = True
            tx["last_alert_at"] = current_jst_string()
            tx["last_alert_ts"] = now_ts
            alert_sent = True

    save_alert_state(state, state_path)
    return alert_sent


def record_transmission_success(
    device_id: str,
    resent_count: int = 0,
    state_path: Path | str | None = None,
    webhook_url: str | None = None,
    line_token: str | None = None,
    line_to: str | None = None,
    post=requests.post,
) -> bool:
    """Record a successful transmission. If recovering from alert state, send recovery message."""
    state = load_alert_state(state_path)
    tx = state["transmission"]

    recovery_sent = False
    if tx["alert_active"]:
        # Calculate outage duration
        duration_str = "unknown"
        if tx["first_failure_at"]:
            try:
                first_dt = datetime.fromisoformat(tx["first_failure_at"])
                seconds = (datetime.now(timezone.utc) - first_dt).total_seconds()
                days = int(seconds // 86400)
                hours = int((seconds % 86400) // 3600)
                mins = int((seconds % 3600) // 60)
                if days > 0:
                    duration_str = f"{days} days {hours} hours"
                elif hours > 0:
                    duration_str = f"{hours} hours {mins} mins"
                else:
                    duration_str = f"{mins} mins"
            except Exception:
                pass

        msg = (
            "✅ Plant IoT Recovered\n\n"
            "Sensor upload resumed successfully.\n\n"
            f"Device:\n{device_id}\n\n"
            f"Recovered after:\n{duration_str}\n\n"
            f"Pending data resent:\n{resent_count} records"
        )
        broadcast_message(
            msg,
            webhook_url=webhook_url,
            line_channel_access_token=line_token,
            line_to_id=line_to,
            post=post,
        )
        recovery_sent = True

    # Reset failure tracking
    tx["consecutive_failures"] = 0
    tx["first_failure_at"] = None
    tx["last_success_at"] = current_jst_string()
    tx["alert_active"] = False
    tx["last_error_summary"] = None

    save_alert_state(state, state_path)
    return recovery_sent
