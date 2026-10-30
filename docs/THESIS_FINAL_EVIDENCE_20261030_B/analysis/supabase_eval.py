#!/usr/bin/env python3
"""Independent recomputation of Supabase operational metrics (distinctions A/B/C).

Inputs (from fetch_supabase.py, read-only GET snapshot):
  ../data/sensor_logs.jsonl
Local read-only input:
  /home/pi/plant-iot/data.db  (outbox_queue; device-side payload + sync time)
Outputs:
  ../results/supabase_metrics.json, ../results/*.csv

Definitions (all times JST = UTC+09:00 unless suffixed _utc):
  Main series      device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float'
  Nominal period   300 s (send_sensor_raspberrypi2.py default, .env SENSOR_INTERVAL_SECONDS)
  Nearest slot     slot = 300*floor((unix+150)/300); a slot is 'filled' if >=1 row maps to it
  Expected slots   half-open [A,B): (B-A)/300 ; inclusive [A,B]: floor((B-A)/300)+1
  A record         row exists in slot
  B valid          temp: not NULL and 0<=t<=50 (85.0 = DS18B20 power-on value, excluded)
                   lux : not NULL and >=0 ; float: state in (water_ok, low_water)
  C cloud arrival  outbox synced_at - created_at (device-side queue, 9/13-10/13 retained)
"""
import csv
import datetime as dt
import json
import sqlite3
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
RES = HERE.parent / "results"
JST = dt.timezone(dt.timedelta(hours=9))
SLOT = 300
MAIN = ("raspberrypi2", "raspberrypi2-ds18b20-bh1750-float")


def J(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=JST)


def ts(s):
    return dt.datetime.fromisoformat(s)


def slot_of(t):
    u = t.timestamp()
    return int(SLOT * ((u + SLOT / 2) // SLOT))


def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def q(vals, p):
    v = sorted(vals)
    if not v:
        return None
    k = (len(v) - 1) * p
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def valid_temp(r):
    t = r["solution_temperature"]
    return t is not None and 0 <= t <= 50


def valid_lux(r):
    return r["light_lux"] is not None and r["light_lux"] >= 0


def valid_float(r):
    return r["float_switch_state"] in ("water_ok", "low_water")


def load():
    rows = []
    for line in open(DATA / "sensor_logs.jsonl"):
        r = json.loads(line)
        r["t"] = ts(r["created_at"]).astimezone(JST)
        rows.append(r)
    return rows


def coverage(main, a, b, inclusive=False):
    """Slot coverage for [a,b) or [a,b]; a,b aligned to 300 s boundaries."""
    ua, ub = int(a.timestamp()), int(b.timestamp())
    end = ub + (SLOT if inclusive else 0)
    expected = set(range(ua, end, SLOT))
    rec, vt, vl, vf, allv = set(), set(), set(), set(), set()
    n_rows = 0
    for r in main:
        s = slot_of(r["t"])
        if s not in expected:
            continue
        n_rows += 1
        rec.add(s)
        if valid_temp(r):
            vt.add(s)
        if valid_lux(r):
            vl.add(s)
        if valid_float(r):
            vf.add(s)
        if valid_temp(r) and valid_lux(r) and valid_float(r):
            allv.add(s)
    e = len(expected)
    return {
        "start": a.isoformat(), "end": b.isoformat(), "inclusive_end": inclusive,
        "rows_mapped": n_rows, "expected_slots": e,
        "A_record_slots": len(rec), "A_record_pct": pct(len(rec), e),
        "B_temp_valid_slots": len(vt), "B_temp_valid_pct": pct(len(vt), e),
        "B_lux_valid_slots": len(vl), "B_lux_valid_pct": pct(len(vl), e),
        "B_float_valid_slots": len(vf), "B_float_valid_pct": pct(len(vf), e),
        "B_all3_valid_slots": len(allv), "B_all3_valid_pct": pct(len(allv), e),
    }


def main():
    RES.mkdir(exist_ok=True)
    rows = load()
    out = {"snapshot_rows_total": len(rows)}
    by_series = Counter((r["device_id"], r["source"]) for r in rows)
    out["series_counts"] = {f"{d}|{s}": n for (d, s), n in by_series.most_common()}
    main = sorted([r for r in rows if (r["device_id"], r["source"]) == MAIN], key=lambda r: (r["t"], r["id"]))
    out["main_count"] = len(main)
    out["main_first"] = main[0]["t"].isoformat()
    out["main_last"] = main[-1]["t"].isoformat()

    # ---- NULL / validity per field (row basis)
    n = len(main)
    fields = {}
    for f in ("solution_temperature", "light_lux", "float_switch_state", "vitality_score"):
        nn = sum(r[f] is None for r in main)
        fields[f] = {"null": nn, "null_pct": pct(nn, n)}
    fields["temp_85C_rows"] = sum(r["solution_temperature"] == 85.0 for r in main)
    fields["temp_valid_rows"] = sum(valid_temp(r) for r in main)
    fields["lux_valid_rows"] = sum(valid_lux(r) for r in main)
    fields["float_valid_rows"] = sum(valid_float(r) for r in main)
    fields["all3_valid_rows"] = sum(valid_temp(r) and valid_lux(r) and valid_float(r) for r in main)
    out["field_quality_rows"] = fields

    last_t = max(r["t"] for r in main if r["solution_temperature"] is not None)
    last_l = max(r["t"] for r in main if r["light_lux"] is not None)
    after = [r for r in main if r["t"] > last_t]
    out["null_onset"] = {
        "last_nonnull_temp": last_t.isoformat(), "last_nonnull_lux": last_l.isoformat(),
        "rows_after_last_temp": len(after),
        "rows_after_with_temp": sum(r["solution_temperature"] is not None for r in after),
        "rows_after_with_lux": sum(r["light_lux"] is not None for r in after),
        "rows_after_with_float": sum(valid_float(r) for r in after),
        "vitality_after_counter": dict(Counter(r["vitality_score"] for r in after).most_common(5)),
        "message_after_counter": dict(Counter(r["message"] for r in after).most_common(3)),
        "rows_around": [
            {k: r[k] for k in ("id", "solution_temperature", "light_lux", "float_switch_state", "vitality_score")}
            | {"t": r["t"].isoformat()}
            for r in main if J("2026-09-09T14:50") <= r["t"] <= J("2026-09-09T15:30")
        ],
    }

    # ---- monthly / daily
    monthly = defaultdict(Counter)
    daily = defaultdict(Counter)
    for r in main:
        for agg, key in ((monthly, r["t"].strftime("%Y-%m")), (daily, r["t"].date().isoformat())):
            agg[key]["rows"] += 1
            agg[key]["temp_valid"] += valid_temp(r)
            agg[key]["lux_valid"] += valid_lux(r)
            agg[key]["float_valid"] += valid_float(r)
            agg[key]["all3_valid"] += valid_temp(r) and valid_lux(r) and valid_float(r)
    with open(RES / "supabase_monthly.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month_jst", "rows", "temp_valid_rows", "lux_valid_rows", "float_valid_rows", "all3_valid_rows"])
        for k in sorted(monthly):
            c = monthly[k]
            w.writerow([k, c["rows"], c["temp_valid"], c["lux_valid"], c["float_valid"], c["all3_valid"]])
    out["monthly"] = {k: dict(v) for k, v in sorted(monthly.items())}

    # daily slot coverage, zero-filled from first to last JST day
    d0, d1 = main[0]["t"].date(), main[-1]["t"].date()
    with open(RES / "supabase_daily.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date_jst", "rows", "expected_slots", "A_record_slots", "A_record_pct",
                    "B_temp_valid_pct", "B_lux_valid_pct", "B_float_valid_pct", "B_all3_valid_pct", "note"])
        d = d0
        daily_cov = {}
        while d <= d1:
            a = dt.datetime.combine(d, dt.time(0), JST)
            b = a + dt.timedelta(days=1)
            note = ""
            if d == d0:
                a = J("2026-06-13T01:20")
                note = "partial(first slot 01:20)"
            if d == d1:
                b = J("2026-10-13T10:40")
                note = "partial(last slot 10:35)"
            c = coverage(main, a, b)
            daily_cov[d.isoformat()] = c
            w.writerow([d.isoformat(), daily[d.isoformat()]["rows"], c["expected_slots"], c["A_record_slots"],
                        c["A_record_pct"], c["B_temp_valid_pct"], c["B_lux_valid_pct"], c["B_float_valid_pct"],
                        c["B_all3_valid_pct"], note])
            d += dt.timedelta(days=1)
    cov_days = [v["A_record_pct"] for v in daily_cov.values()]
    out["daily_summary"] = {
        "days": len(cov_days),
        "days_A_ge_99pct": sum(x >= 99 for x in cov_days),
        "days_A_zero": sum(x == 0 for x in cov_days),
        "days_all3_ge_99pct": sum(v["B_all3_valid_pct"] >= 99 for v in daily_cov.values()),
    }

    # ---- coverage windows
    win = {
        "full_record_span [6/13 01:20,10/13 10:40)": (J("2026-06-13T01:20"), J("2026-10-13T10:40"), False),
        "user_preaccident [7/22 00:00,8/2 19:15)": (J("2026-07-22T00:00"), J("2026-08-02T19:15"), False),
        "formal_post_recovery [7/22 13:05,8/2 19:15] inclusive": (J("2026-07-22T13:05"), J("2026-08-02T19:15"), True),
        "P1 initial [6/13 01:20,7/11 15:45)": (J("2026-06-13T01:20"), J("2026-07-11T15:45"), False),
        "P3 post-accident [8/7 17:05,9/9 15:10)": (J("2026-08-07T17:05"), J("2026-09-09T15:10"), False),
        "P4 sensors-null [9/9 15:10,10/13 10:40)": (J("2026-09-09T15:10"), J("2026-10-13T10:40"), False),
    }
    for m in ("2026-06", "2026-07", "2026-08", "2026-09", "2026-10"):
        y, mo = map(int, m.split("-"))
        a = dt.datetime(y, mo, 1, tzinfo=JST)
        b = dt.datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=JST)
        a = max(a, J("2026-06-13T01:20"))
        b = min(b, J("2026-10-13T10:40"))
        win[f"month {m}"] = (a, b, False)
    out["coverage"] = {k: coverage(main, a, b, inc) for k, (a, b, inc) in win.items()}

    # ---- gaps
    gaps = []
    for p, c in zip(main, main[1:]):
        gaps.append(((c["t"] - p["t"]).total_seconds(), p["t"], c["t"]))
    iv = [g[0] for g in gaps]
    out["intervals_s"] = {
        "n": len(iv), "median": round(st.median(iv), 3), "p05": round(q(iv, .05), 3),
        "p95": round(q(iv, .95), 3), "lt60": sum(x < 60 for x in iv), "gt600": sum(x > 600 for x in iv),
    }
    out["top_gaps"] = [
        {"from": a.isoformat(), "to": b.isoformat(), "seconds": round(s, 3), "hours": round(s / 3600, 2)}
        for s, a, b in sorted(gaps, key=lambda g: -g[0])[:8]
    ]

    # ---- C: device-side outbox vs cloud
    con = sqlite3.connect("file:/home/pi/plant-iot/data.db?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    ob = con.execute("SELECT id,payload,status,retry_count,created_at,synced_at FROM outbox_queue ORDER BY id").fetchall()
    con.close()
    lat, retried, payload_null_both = [], 0, 0
    cloud_ts = {r["t"].astimezone(dt.timezone.utc).isoformat(timespec="microseconds") for r in main}
    matched = 0
    ob_times = []
    for _id, payload, status, rc, created, synced in ob:
        p = json.loads(payload)
        c_utc = dt.datetime.fromisoformat(created).replace(tzinfo=dt.timezone.utc)
        s_utc = dt.datetime.fromisoformat(synced) if synced else None
        if s_utc:
            lat.append((s_utc - c_utc).total_seconds())
        retried += rc > 0
        payload_null_both += p.get("solution_temperature") is None and p.get("light_lux") is None
        pt = dt.datetime.fromisoformat(p["created_at"]).astimezone(dt.timezone.utc)
        ob_times.append(pt)
        matched += pt.isoformat(timespec="microseconds") in cloud_ts
    lo, hi = min(ob_times), max(ob_times)
    cloud_in_window = sum(lo <= r["t"] <= hi for r in main)
    out["C_outbox"] = {
        "note": "outbox created_at is SQLite CURRENT_TIMESTAMP (UTC, 1 s resolution); synced_at is ISO UTC",
        "rows": len(ob), "status": dict(Counter(o[2] for o in ob)),
        "payload_window_utc": [lo.isoformat(), hi.isoformat()],
        "rows_retried": retried,
        "payload_temp_and_lux_null": payload_null_both,
        "matched_in_cloud_by_exact_timestamp": matched,
        "cloud_rows_in_same_window": cloud_in_window,
        "latency_s": {
            "n": len(lat), "median": round(st.median(lat), 3), "p95": round(q(lat, .95), 3),
            "p99": round(q(lat, .99), 3), "max": round(max(lat), 3),
            "le_5s": sum(x <= 5 for x in lat), "le_60s": sum(x <= 60 for x in lat),
            "gt_60s": sum(x > 60 for x in lat),
            "le_5s_pct": pct(sum(x <= 5 for x in lat), len(lat)),
        },
    }
    with open(RES / "outbox_latency_s.csv", "w") as f:
        f.write("latency_s\n" + "\n".join(f"{x:.6f}" for x in lat) + "\n")

    (RES / "supabase_metrics.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({k: out[k] for k in out if k not in ("monthly",)}, indent=1, ensure_ascii=False, default=str)[:9000])


if __name__ == "__main__":
    main()
