#!/usr/bin/env python3
"""Comprehensive Supabase Health Check, Heartbeat, and Raspberry Pi Self-Monitoring."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from alert_manager import broadcast_message, load_alert_state, save_alert_state

load_dotenv()


def _masked_key_label(key: str) -> str:
    if not key:
        return "unset"
    return f"set len={len(key)} prefix={key[:8]} suffix={key[-4:]}"


def health_check(http_client=requests) -> dict[str, Any]:
    """Check Supabase REST API connection."""
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SENSOR_KEY", "")
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


def check_device_heartbeat(
    device_id: str = "raspberrypi2", http_client=requests
) -> dict[str, Any]:
    """Check the age of the latest sensor_log for the specified device."""
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SENSOR_KEY", "")

    endpoint = (
        f"{supabase_url}/rest/v1/sensor_logs"
        f"?select=id,created_at&device_id=eq.{device_id}&order=created_at.desc&limit=1"
    )
    response = http_client.get(
        endpoint,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        timeout=10,
    )
    response.raise_for_status()
    rows = response.json()
    latest = rows[0] if isinstance(rows, list) and rows else None

    if not latest or not latest.get("created_at"):
        return {
            "device_id": device_id,
            "status": "CRITICAL",
            "age_minutes": None,
            "message": "No sensor data found in Supabase",
        }

    raw_ts = latest["created_at"].replace("Z", "+00:00")
    created_at_dt = datetime.fromisoformat(raw_ts)
    now_dt = datetime.now(timezone.utc)
    age_seconds = max(0.0, (now_dt - created_at_dt).total_seconds())
    age_minutes = round(age_seconds / 60.0, 1)

    if age_minutes <= 15:
        status = "OK"
    elif age_minutes <= 60:
        status = "WARNING"
    else:
        status = "CRITICAL"

    return {
        "device_id": device_id,
        "status": status,
        "age_minutes": age_minutes,
        "latest_created_at": latest["created_at"],
    }


def get_cpu_temperature() -> float | None:
    """Read Raspberry Pi CPU temperature in Celsius."""
    temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if temp_path.exists():
        try:
            return round(int(temp_path.read_text().strip()) / 1000.0, 1)
        except Exception:
            pass
    try:
        res = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True)
        if res.returncode == 0 and "temp=" in res.stdout:
            val = res.stdout.strip().split("=")[1].replace("'C", "")
            return float(val)
    except Exception:
        pass
    return None


def get_memory_usage_percent() -> float | None:
    """Read memory usage percentage from /proc/meminfo."""
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return None
    try:
        lines = meminfo_path.read_text().splitlines()
        mem_total = None
        mem_avail = None
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1])
        if mem_total and mem_avail:
            used = mem_total - mem_avail
            return round((used / mem_total) * 100.0, 1)
    except Exception:
        pass
    return None


def check_system_health() -> dict[str, Any]:
    """Check systemd service, disk space, CPU temperature, and memory usage."""
    device_id = os.getenv("DEVICE_ID", "raspberrypi2")
    service_name = f"plant-sensor-{device_id}.service"

    # 1. Systemd service status
    service_active = False
    try:
        res = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
        )
        service_active = res.stdout.strip() == "active"
    except Exception:
        service_active = False

    # 2. Disk space
    total, used, free = shutil.disk_usage("/")
    disk_percent = round((used / total) * 100.0, 1)

    # 3. CPU Temperature & Memory
    cpu_temp = get_cpu_temperature()
    mem_percent = get_memory_usage_percent()

    issues = []
    if not service_active:
        issues.append(f"systemd service '{service_name}' is NOT running")
    if disk_percent >= 90.0:
        issues.append(f"Disk space usage critical: {disk_percent}%")
    if cpu_temp is not None and cpu_temp >= 80.0:
        issues.append(f"CPU temperature high: {cpu_temp}°C")
    if mem_percent is not None and mem_percent >= 90.0:
        issues.append(f"Memory usage high: {mem_percent}%")

    return {
        "service_name": service_name,
        "service_active": service_active,
        "disk_percent": disk_percent,
        "cpu_temp_c": cpu_temp,
        "mem_percent": mem_percent,
        "status": "CRITICAL" if not service_active or disk_percent >= 95.0 else ("WARNING" if issues else "OK"),
        "issues": issues,
    }


def run_monitoring_cycle(http_client=requests, alert_state_path=None) -> dict[str, Any]:
    """Run full health, heartbeat, and system check, sending notifications on issues."""
    device_id = os.getenv("DEVICE_ID", "raspberrypi2")
    result = {}

    try:
        result["supabase_api"] = health_check(http_client)
    except Exception as exc:
        result["supabase_api"] = {"ok": False, "error": str(exc)}

    try:
        hb = check_device_heartbeat(device_id, http_client)
        result["heartbeat"] = hb
    except Exception as exc:
        result["heartbeat"] = {"status": "CRITICAL", "error": str(exc)}

    sys_health = check_system_health()
    result["system_health"] = sys_health

    # Evaluate notification rules for Heartbeat & System
    state = load_alert_state(alert_state_path)
    hb_status = result["heartbeat"].get("status")
    sys_status = sys_health.get("status")

    # Heartbeat Alerts (30min -> Warning, 60min -> Critical)
    if hb_status in ("WARNING", "CRITICAL"):
        hb_info = result["heartbeat"]
        age_str = f"{hb_info.get('age_minutes')} minutes" if hb_info.get('age_minutes') else "Unknown"
        level_icon = "🚨" if hb_status == "CRITICAL" else "⚠️"

        msg = (
            f"{level_icon} Plant IoT Heartbeat {hb_status}\n\n"
            f"No sensor data uploaded for {device_id} in {age_str}.\n\n"
            f"Device: {device_id}\n"
            f"Status: {hb_status}\n"
            f"Last uploaded at: {hb_info.get('latest_created_at', 'None')}\n\n"
            "Action recommended: Check Raspberry Pi service & network connection"
        )
        if not state["heartbeat"].get("alert_active"):
            broadcast_message(msg)
            state["heartbeat"]["alert_active"] = True
            state["heartbeat"]["last_alert_at"] = datetime.now(timezone.utc).isoformat()
    elif hb_status == "OK" and state["heartbeat"].get("alert_active"):
        msg = (
            f"✅ Plant IoT Heartbeat Recovered\n\n"
            f"Sensor data uploads for {device_id} have resumed normally."
        )
        broadcast_message(msg)
        state["heartbeat"]["alert_active"] = False

    # System Health Alerts
    if sys_status in ("WARNING", "CRITICAL") and sys_health.get("issues"):
        issues_text = "\n".join(f"• {issue}" for issue in sys_health["issues"])
        msg = (
            f"🚨 Plant IoT System Alert ({device_id})\n\n"
            f"System monitoring detected issues:\n\n"
            f"{issues_text}\n\n"
            f"CPU Temp: {sys_health.get('cpu_temp_c')}°C | Disk: {sys_health.get('disk_percent')}% | Mem: {sys_health.get('mem_percent')}%"
        )
        if not state["system"].get("alert_active"):
            broadcast_message(msg)
            state["system"]["alert_active"] = True
            state["system"]["last_alert_at"] = datetime.now(timezone.utc).isoformat()
    elif sys_status == "OK" and state["system"].get("alert_active"):
        msg = (
            f"✅ Plant IoT System Recovered\n\n"
            f"System parameters on {device_id} returned to normal thresholds."
        )
        broadcast_message(msg)
        state["system"]["alert_active"] = False

    save_alert_state(state, alert_state_path)
    return result


def main() -> int:
    res = run_monitoring_cycle()
    hb = res.get("heartbeat", {})
    sys_h = res.get("system_health", {})
    print(
        "monitoring check complete: "
        f"hb_status={hb.get('status')} (age={hb.get('age_minutes')}m) "
        f"sys_status={sys_h.get('status')} "
        f"issues={len(sys_h.get('issues', []))}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
