#!/usr/bin/env python3
"""Read-only export of raspi2 Outbox timing fields (run on raspi2; stdout=CSV).
Payload is parsed only for its measurement timestamp; no other payload content exported."""
import csv, json, sqlite3, sys
db = sqlite3.connect("file:/home/pi/plant-iot/data.db?mode=ro", uri=True)
db.execute("PRAGMA query_only=ON")
w = csv.writer(sys.stdout)
w.writerow(["id","status","retry_count","queued_at_utc","synced_at_utc","measured_at","has_last_error"])
for i, st, rc, ca, sa, p, le in db.execute("SELECT id,status,retry_count,created_at,synced_at,payload,last_error FROM outbox_queue ORDER BY id"):
    w.writerow([i, st, rc, ca, sa, json.loads(p).get("created_at"), int(bool(le))])
