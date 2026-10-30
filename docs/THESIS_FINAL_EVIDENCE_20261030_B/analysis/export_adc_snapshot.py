#!/usr/bin/env python3
"""Read-only fixed snapshot of the live moisture-logger SQLite.

Opens readings.sqlite3 with mode=ro + PRAGMA query_only inside one read
transaction (WAL-consistent), keeps rows with observed_at < CUTOFF_UTC and
writes ../data/adc_snapshot.csv, ../data/observation_events.csv and
../data/sqlite_schema.json. The live logger keeps appending; it is not touched.
"""
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

DB = "/home/pi/plant-iot-moisture/readings.sqlite3"
CUTOFF_UTC = "2026-10-30T08:00:00.000+00:00"  # = 2026-10-30 17:00:00 JST
OUT = Path(__file__).resolve().parent.parent / "data"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    con.execute("BEGIN")
    schema = [dict(type=t, name=n, sql=s) for t, n, s in
              con.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")]
    total_live = con.execute("SELECT COUNT(*), MAX(observed_at_utc) FROM adc_readings").fetchone()
    cols = [r[1] for r in con.execute("PRAGMA table_info(adc_readings)")]
    rows = con.execute("SELECT * FROM adc_readings WHERE observed_at_utc < ? ORDER BY id",
                       (CUTOFF_UTC,)).fetchall()
    events = con.execute("SELECT * FROM observation_events ORDER BY id").fetchall()
    integrity = con.execute("PRAGMA quick_check").fetchone()[0]
    con.execute("COMMIT")
    con.close()

    with open(OUT / "adc_snapshot.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    with open(OUT / "observation_events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "noted_at_utc", "note"])
        w.writerows(events)
    sha = hashlib.sha256((OUT / "adc_snapshot.csv").read_bytes()).hexdigest()
    meta = {
        "db": DB,
        "cutoff_utc_exclusive": CUTOFF_UTC,
        "live_total_rows_at_read": total_live[0],
        "live_max_observed_at_utc_at_read": total_live[1],
        "snapshot_rows": len(rows),
        "events": len(events),
        "quick_check": integrity,
        "snapshot_sha256": sha,
        "schema": schema,
    }
    (OUT / "sqlite_schema.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in meta.items() if k != "schema"}, indent=2))


if __name__ == "__main__":
    main()
