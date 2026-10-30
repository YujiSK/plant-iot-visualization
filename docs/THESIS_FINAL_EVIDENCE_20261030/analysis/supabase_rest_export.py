#!/usr/bin/env python3
"""Read-only Supabase REST export (run on raspi2). GET only; credentials read from
/home/pi/plant-iot/.env and never printed. Usage: python3 -I - TABLE [probe] < this
Writes JSON lines to stdout."""
import json, sys, urllib.request, urllib.parse
env = {}
for line in open("/home/pi/plant-iot/.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
base = env["SUPABASE_URL"].rstrip("/") + "/rest/v1/"
key = env["SUPABASE_KEY"]
table = sys.argv[1]; probe = len(sys.argv) > 2
def get(params, extra=None):
    req = urllib.request.Request(base + table + "?" + urllib.parse.urlencode(params),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Prefer": "count=exact", **(extra or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()), r.headers.get("Content-Range")
if probe:
    rows, cr = get({"select": "*", "limit": 1, "order": "id"})
    print(json.dumps({"content_range": cr, "columns": list(rows[0].keys()) if rows else []}))
    sys.exit()
off, page = 0, 1000
while True:
    rows, cr = get({"select": "*", "order": "id", "limit": page, "offset": off})
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    if len(rows) < page: break
    off += page
print(json.dumps({"__content_range__": cr}))
