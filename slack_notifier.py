#!/usr/bin/env python3
"""Send stateful Plant IoT alerts to Slack without stopping sensor collection."""

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import requests


DEFAULT_STATE_PATH = Path(__file__).with_name("notification_state.json")
DEFAULT_STATE = {
    "low_water": {
        "active": False,
        "last_alert_at": None,
        "last_recovery_at": None,
        "last_state": None,
        "water_ok_streak": 0,
    }
}


def current_timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_notification_state(path=None):
    state_path = Path(path or os.getenv("NOTIFICATION_STATE_PATH") or DEFAULT_STATE_PATH)
    state = deepcopy(DEFAULT_STATE)
    if not state_path.exists():
        return state

    with state_path.open(encoding="utf-8") as state_file:
        saved_state = json.load(state_file)

    saved_low_water = saved_state.get("low_water", {})
    if isinstance(saved_low_water, dict):
        state["low_water"].update(saved_low_water)
    return state


def save_notification_state(state, path=None):
    state_path = Path(path or os.getenv("NOTIFICATION_STATE_PATH") or DEFAULT_STATE_PATH)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, ensure_ascii=False, indent=2)
        state_file.write("\n")
    temporary_path.replace(state_path)


def detect_alerts(payload, state, recovery_confirmations=2):
    """Return notification events and update transition counters in state."""
    if payload.get("device_id") != "raspberrypi2":
        return []

    current_state = payload.get("float_switch_state")
    if current_state not in {"low_water", "water_ok"}:
        return []

    low_water = state["low_water"]
    events = []

    if current_state == "low_water":
        low_water["water_ok_streak"] = 0
        low_water["last_state"] = "low_water"
        events.append("duplicate_low_water" if low_water.get("active") else "low_water")
        return events

    if low_water.get("active"):
        low_water["water_ok_streak"] = int(low_water.get("water_ok_streak", 0)) + 1
        if low_water["water_ok_streak"] >= max(1, recovery_confirmations):
            events.append("water_ok")
    else:
        low_water["water_ok_streak"] = 0
    low_water["last_state"] = "water_ok"
    return events


def format_value(value, suffix=""):
    return "取得不可" if value is None else f"{value}{suffix}"


def build_slack_message(event, payload, occurred_at=None):
    occurred_at = occurred_at or current_timestamp()
    common = (
        f"device: {payload.get('device_id', 'unknown')}\n"
        f"location: {payload.get('location_id', 'unknown')}\n"
        f"状態: {event}\n"
        f"vitality: {format_value(payload.get('vitality_score'))}\n"
        f"養液温度: {format_value(payload.get('solution_temperature'), '℃')}\n"
    )

    if event == "low_water":
        return (
            "【Plant IoT Alert】\n\n"
            "2号機の貯水部が低水位です。\n\n"
            f"{common}"
            f"照度: {format_value(payload.get('light_lux'), ' lx')}\n"
            f"時刻: {occurred_at}\n\n"
            "確認してください:\n"
            "・貯水部の水位\n"
            "・フロートスイッチの位置\n"
            "・チューブや配線の抜け\n"
            "・培地表面の湿潤状態と、貯水部の水位は分けて確認する"
        )

    return (
        "【Plant IoT Recovery】\n\n"
        "2号機の水位が正常に戻りました。\n\n"
        f"{common}"
        f"時刻: {occurred_at}\n\n"
        "次の段階では、この回復イベントをcare_logsへ自動記録します。"
    )


def send_slack_message(message, webhook_url=None, post=requests.post):
    webhook_url = webhook_url if webhook_url is not None else os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        print("[slack] disabled: SLACK_WEBHOOK_URL not set", flush=True)
        return False

    try:
        response = post(webhook_url, json={"text": message}, timeout=10)
        response.raise_for_status()
        return True
    except Exception as exc:
        print(f"[slack] failed: {type(exc).__name__}: {exc}", flush=True)
        return False


def process_notifications(
    payload,
    state_path=None,
    webhook_url=None,
    post=requests.post,
    recovery_confirmations=2,
):
    """Detect transitions, send Slack messages, and persist notification state."""
    try:
        state = load_notification_state(state_path)
    except Exception as exc:
        print(f"[slack] failed: state load: {type(exc).__name__}: {exc}", flush=True)
        state = deepcopy(DEFAULT_STATE)

    events = detect_alerts(payload, state, recovery_confirmations)
    low_water = state["low_water"]

    for event in events:
        if event == "duplicate_low_water":
            print("[slack] skipped: duplicate low_water", flush=True)
            continue

        occurred_at = current_timestamp()
        sent = send_slack_message(
            build_slack_message(event, payload, occurred_at),
            webhook_url=webhook_url,
            post=post,
        )
        if not sent:
            continue

        if event == "low_water":
            low_water["active"] = True
            low_water["last_alert_at"] = occurred_at
            print("[slack] alert sent: low_water", flush=True)
        else:
            low_water["active"] = False
            low_water["last_recovery_at"] = occurred_at
            low_water["water_ok_streak"] = 0
            print("[slack] recovery sent: water_ok", flush=True)

    try:
        save_notification_state(state, state_path)
    except Exception as exc:
        print(f"[slack] failed: state save: {type(exc).__name__}: {exc}", flush=True)

    return events
