#!/usr/bin/env python3
"""Read-only export of Supabase tables via PostgREST GET.

- Loads SUPABASE_URL / SUPABASE_KEY from /home/pi/plant-iot/.env without printing them.
- Only HTTP GET is issued (no INSERT/UPDATE/DELETE/RPC).
- Writes JSON-lines snapshots to ../data/ for offline recomputation.

Usage: python3 fetch_supabase.py
"""
import json
import sys
from pathlib import Path

import requests

ENV = Path("/home/pi/plant-iot/.env")
OUT = Path(__file__).resolve().parent.parent / "data"
PAGE = 1000

TABLES = {
    # table: (select, order)
    "sensor_logs": ("*", "id.asc"),
    "care_logs": ("*", "created_at.asc"),
    "plant_observations": ("*", "observed_at.asc"),
}


def load_env():
    env = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    env = load_env()
    base = env["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
    key = env.get("SUPABASE_KEY") or env["SUPABASE_SENSOR_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "count=exact"}
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for table, (select, order) in TABLES.items():
        rows, offset, total = [], 0, None
        while True:
            h = dict(headers, Range=f"{offset}-{offset + PAGE - 1}")
            r = requests.get(base + table, params={"select": select, "order": order},
                             headers=h, timeout=60)
            if r.status_code not in (200, 206):
                print(f"{table}: HTTP {r.status_code} {r.text[:200]}", file=sys.stderr)
                break
            cr = r.headers.get("Content-Range", "")
            if "/" in cr and cr.split("/")[1] != "*":
                total = int(cr.split("/")[1])
            batch = r.json()
            rows.extend(batch)
            offset += len(batch)
            if not batch or (total is not None and offset >= total):
                break
        with open(OUT / f"{table}.jsonl", "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        summary[table] = {"fetched": len(rows), "content_range_total": total}
        print(table, summary[table])
    (OUT / "fetch_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
