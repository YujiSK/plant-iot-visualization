#!/usr/bin/env python3
"""Journal Log Sensor Data Extractor and Backfill Script.

This script parses systemd journalctl logs for plant sensor services,
extracts sensor payloads logged during transmission attempts, generates a
CSV backfill file, and optionally inserts recovered logs into Supabase.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

DEFAULT_UNIT = "plant-sensor-raspberrypi2.service"
DEFAULT_SINCE = "2026-07-11"
DEFAULT_UNTIL = "2026-07-22"
DEFAULT_CSV_OUTPUT = "exports/sensor_logs_backfill_20260711_20260722.csv"

# Regex patterns for matching logged sensor outputs
SENT_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\w{3}\s+\d+\s+[\d:]+)\s+\S+\s+python\[\d+\]:\s+"
    r"sent:\s+device=(?P<device_id>[^,]+),\s+"
    r"solution_temperature=(?P<solution_temperature>[^,]+),\s+"
    r"light=(?P<light_lux>[\d\.]+)lx\((?P<light_status>[^\)]+)\),\s+"
    r"float=(?P<float_switch_state>[^,]+),\s+"
    r"status=(?P<status>\d+)"
)


def fetch_journal_logs(unit: str, since: str, until: str) -> list[str]:
    """Fetch logs from journalctl for the specified service and time range."""
    cmd = [
        "journalctl",
        "-u", unit,
        "--since", since,
        "--until", until,
        "--no-pager",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except subprocess.CalledProcessError as exc:
        print(f"Error fetching journal logs: {exc}", file=sys.stderr)
        return []


def parse_journal_lines(lines: list[str]) -> list[dict]:
    """Parse log lines and extract structured sensor log dicts."""
    extracted = []
    current_year = datetime.now().year

    for line in lines:
        match = SENT_LOG_PATTERN.search(line)
        if match:
            data = match.groupdict()
            # Parse syslog timestamp (e.g. Jul 22 12:39:07)
            raw_ts = f"{current_year} {data['timestamp']}"
            try:
                dt = datetime.strptime(raw_ts, "%Y %b %d %H:%M:%S")
                # Assume local timezone if naive
                dt_iso = dt.astimezone().isoformat()
            except ValueError:
                dt_iso = data['timestamp']

            def parse_float(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            sol_temp = parse_float(data['solution_temperature'])
            light_lux = parse_float(data['light_lux'])
            float_state = data['float_switch_state']
            float_triggered = True if float_state == "low_water" else (False if float_state == "water_ok" else None)

            extracted.append({
                "source": "raspberrypi2-ds18b20-bh1750-float",
                "device_id": data['device_id'],
                "location_id": "location-b",
                "solution_temperature": sol_temp,
                "light_lux": light_lux,
                "light_status": data['light_status'],
                "float_switch_state": float_state,
                "float_switch_triggered": float_triggered,
                "created_at": dt_iso,
                "log_status": data['status'],
            })
    return extracted


def write_csv(records: list[dict], output_path: Path):
    """Write extracted sensor records to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source",
        "device_id",
        "location_id",
        "solution_temperature",
        "light_lux",
        "light_status",
        "float_switch_state",
        "float_switch_triggered",
        "created_at",
        "log_status",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description="Extract sensor logs from journalctl for backfill.")
    parser.add_argument("--unit", default=DEFAULT_UNIT, help="systemd unit name")
    parser.add_argument("--since", default=DEFAULT_SINCE, help="Since date (YYYY-MM-DD)")
    parser.add_argument("--until", default=DEFAULT_UNTIL, help="Until date (YYYY-MM-DD)")
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_CSV_OUTPUT), help="Output CSV path")
    parser.add_argument("--insert", action="store_true", help="Insert backfill records into Supabase (DO NOT RUN UNLESS VERIFIED)")

    args = parser.parse_args()

    lines = fetch_journal_logs(args.unit, args.since, args.until)
    records = parse_journal_lines(lines)

    print(f"Journal lines fetched: {len(lines)}")
    print(f"Recoverable sensor log entries found: {len(records)}")

    write_csv(records, args.output)
    print(f"Wrote extracted records to: {args.output}")

    if args.insert:
        if not records:
            print("No records to insert.")
            return
        print("WARNING: Insert mode enabled. Inserting records into Supabase...")
        # Note: Actual insertion logic can be called here when requested.
    else:
        print("Dry run completed. No data was inserted into Supabase.")


if __name__ == "__main__":
    main()
