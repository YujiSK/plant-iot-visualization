#!/usr/bin/env python3
"""Write automatic management-support events to Supabase care_logs."""

import os

import requests


def build_recovery_care_log(payload, occurred_at):
    return {
        "action_type": "checked",
        "note": (
            "自動記録: 2号機のフロートスイッチがlow_waterから"
            f"water_okへ回復しました。device={payload.get('device_id')}, "
            f"location={payload.get('location_id')}, detected_at={occurred_at}"
        ),
        "vitality_score": payload.get("vitality_score"),
        "message": "フロートスイッチによる水位回復検知",
    }


def send_recovery_care_log(payload, occurred_at, post=requests.post):
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    sensor_key = os.getenv("SUPABASE_SENSOR_KEY", "")
    if not supabase_url or not sensor_key:
        print("[care] disabled: Supabase settings not set", flush=True)
        return False

    try:
        response = post(
            f"{supabase_url}/rest/v1/care_logs",
            json=build_recovery_care_log(payload, occurred_at),
            headers={
                "apikey": sensor_key,
                "Authorization": f"Bearer {sensor_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            timeout=10,
        )
        response.raise_for_status()
        print("[care] recovery recorded: water_ok", flush=True)
        return True
    except Exception as exc:
        print(f"[care] failed: {type(exc).__name__}: {exc}", flush=True)
        return False
