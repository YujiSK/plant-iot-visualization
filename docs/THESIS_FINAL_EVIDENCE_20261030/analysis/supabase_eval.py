#!/usr/bin/env python3
"""Supabase operational evaluation (A: record exists / B: valid sensor value / C: cloud arrival).

Definitions
- Population: public.sensor_logs rows with device_id=raspberrypi2 AND
  source=raspberrypi2-ds18b20-bh1750-float ("main series"). created_at is the
  measurement time written by the device (payload created_at), not DB insert time.
- Nominal period 300 s. Nearest-slot rule: UNIX second t -> 300*floor((t+150)/300),
  tolerance [-150,+150) s. Multiple rows in one slot count once.
- Expected slots for half-open window [A,B): slot times s with A <= s < B
  (A,B on 5-minute boundaries -> (B-A)/300).
- Valid value (B): temperature non-NULL and 0<=T<=50 C (excludes the four 85.0 C
  DS18B20 power-on/error candidates); light_lux non-NULL and >=0;
  float_switch_state in {water_ok, low_water}. A slot is valid for a sensor if
  any row in that slot has a valid value.
- C (cloud arrival latency): only measurable from the raspi2 Outbox
  (synced_at - measured_at), retained 2026-09-13..10-13.
Timezone: all day/month boundaries are JST (UTC+09:00).
"""
import collections
import csv
import datetime as dt
import statistics as st

from common import (DATA, JST, MAIN_DEVICE, MAIN_SOURCE, fmt, jst, load_jsonl,
                    parse_ts, write_json, RESULTS)

SLOT = 300
rows_all = load_jsonl(DATA / "supabase_sensor_logs.jsonl")
out = {"population_total_rows": len(rows_all)}

# ---- series inventory (device/sensor configuration history) ----
series = collections.defaultdict(list)
for r in rows_all:
    series[(r["device_id"], r["source"])].append(parse_ts(r["created_at"]))
out["series"] = sorted(
    [{"device_id": k[0], "source": k[1], "rows": len(v), "first": fmt(min(v)), "last": fmt(max(v))}
     for k, v in series.items()], key=lambda x: x["first"])

main = sorted((r for r in rows_all if r["device_id"] == MAIN_DEVICE and r["source"] == MAIN_SOURCE),
              key=lambda r: r["created_at"])
for r in main:
    r["_t"] = parse_ts(r["created_at"])
out["main_rows"] = len(main)
out["main_first"], out["main_last"] = fmt(main[0]["_t"]), fmt(main[-1]["_t"])


def temp_ok(r):
    v = r["solution_temperature"]
    return v is not None and 0 <= v <= 50


def lux_ok(r):
    v = r["light_lux"]
    return v is not None and v >= 0


def float_ok(r):
    return r["float_switch_state"] in ("water_ok", "low_water")


SENSORS = {"temperature": temp_ok, "light_lux": lux_ok, "float": float_ok}

# ---- row-level NULL / validity by month ----
by_month = collections.defaultdict(list)
for r in main:
    by_month[r["_t"].astimezone(JST).strftime("%Y-%m")].append(r)
monthly = []
for m, rs in sorted(by_month.items()):
    n = len(rs)
    monthly.append({
        "month": m, "rows": n,
        "temp_null_pct": round(100 * sum(r["solution_temperature"] is None for r in rs) / n, 2),
        "lux_null_pct": round(100 * sum(r["light_lux"] is None for r in rs) / n, 2),
        "float_null_pct": round(100 * sum(r["float_switch_state"] is None for r in rs) / n, 2),
        "temp_85_rows": sum(r["solution_temperature"] == 85.0 for r in rs),
    })
out["monthly_rows"] = monthly
n = len(main)
out["row_level_overall"] = {
    k: {"null_rows": sum(r[c] is None for r in main), "null_pct": round(100 * sum(r[c] is None for r in main) / n, 2)}
    for k, c in [("temperature", "solution_temperature"), ("light_lux", "light_lux"), ("float", "float_switch_state")]}
out["temp_out_of_screen_rows"] = sum(r["solution_temperature"] is not None and not temp_ok(r) for r in main)
for k, c in [("temperature", "solution_temperature"), ("light_lux", "light_lux")]:
    nn = [r["_t"] for r in main if r[c] is not None]
    out[f"{k}_last_non_null"] = fmt(max(nn))

# ---- slot table ----
slots = collections.defaultdict(lambda: {"rows": 0, **{s: False for s in SENSORS}})
for r in main:
    t = r["_t"].timestamp()
    s = SLOT * int((t + SLOT / 2) // SLOT)
    e = slots[s]
    e["rows"] += 1
    for k, f in SENSORS.items():
        e[k] = e[k] or f(r)


def window(name, A, B, note=""):
    a, b = int(A.timestamp()), int(B.timestamp())
    exp = list(range(a, b, SLOT))
    rec = [s for s in exp if s in slots]
    res = {"window": name, "start": fmt(A), "end_exclusive": fmt(B), "note": note,
           "expected_slots": len(exp), "A_record_slots": len(rec),
           "A_record_pct": round(100 * len(rec) / len(exp), 2) if exp else None,
           "raw_rows_in_window": sum(A <= r["_t"] < B for r in main)}
    for k in SENSORS:
        v = sum(1 for s in rec if slots[s][k])
        res[f"B_{k}_valid_slots"] = v
        res[f"B_{k}_valid_pct"] = round(100 * v / len(exp), 2) if exp else None
    allv = sum(1 for s in rec if all(slots[s][k] for k in SENSORS))
    res["B_all3_valid_slots"] = allv
    res["B_all3_valid_pct"] = round(100 * allv / len(exp), 2) if exp else None
    return res


W = [
    window("全記録範囲", jst(2026, 6, 13, 1, 20), jst(2026, 10, 13, 10, 40), "主要系列の最初～最後を覆う5分枠"),
    window("指定区間(事故前・半開区間)", jst(2026, 7, 22), jst(2026, 8, 2, 19, 15), "先行監査95.44%の再現"),
    window("復旧後評価区間(端点含む)", jst(2026, 7, 22, 13, 5), jst(2026, 8, 2, 19, 20), "7/22 13:05～8/2 19:15の期待時刻を両端含む=3,243枠"),
    window("P1 設置～認証障害前", jst(2026, 6, 13, 1, 20), jst(2026, 7, 11, 15, 45)),
    window("P2 認証障害期", jst(2026, 7, 11, 15, 45), jst(2026, 7, 22, 13, 5)),
    window("P3 復旧後～転倒前", jst(2026, 7, 22, 13, 5), jst(2026, 8, 2, 19, 20)),
    window("P4 転倒後～記録再開", jst(2026, 8, 2, 19, 20), jst(2026, 8, 7, 17, 5)),
    window("P5 再開～9/9欠損発生前", jst(2026, 8, 7, 17, 5), jst(2026, 9, 9, 15, 10)),
    window("P6 9/9欠損発生後", jst(2026, 9, 9, 15, 10), jst(2026, 10, 13, 10, 40)),
]
out["windows"] = W

# ---- daily (JST) slot coverage, restricted to the full-record window ----
A0, B0 = jst(2026, 6, 13, 1, 20), jst(2026, 10, 13, 10, 40)
daily = []
d = A0.date()
while d <= (B0 - dt.timedelta(seconds=1)).date():
    s0 = max(A0, dt.datetime(d.year, d.month, d.day, tzinfo=JST))
    s1 = min(B0, dt.datetime(d.year, d.month, d.day, tzinfo=JST) + dt.timedelta(days=1))
    w = window(d.isoformat(), s0, s1)
    daily.append({"date": d.isoformat(), "expected": w["expected_slots"], "raw_rows": w["raw_rows_in_window"],
                  "A_pct": w["A_record_pct"], "B_temp_pct": w["B_temperature_valid_pct"],
                  "B_lux_pct": w["B_light_lux_valid_pct"], "B_float_pct": w["B_float_valid_pct"],
                  "B_all3_pct": w["B_all3_valid_pct"]})
    d += dt.timedelta(days=1)
with open(RESULTS / "supabase_daily_coverage.csv", "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(daily[0].keys()))
    wr.writeheader(); wr.writerows(daily)
out["days_total"] = len(daily)
out["days_A_ge_99pct"] = sum(x["A_pct"] >= 99 for x in daily)
out["days_A_zero"] = sum(x["A_pct"] == 0 for x in daily)
out["days_all3_ge_99pct"] = sum(x["B_all3_pct"] >= 99 for x in daily)
# monthly slot coverage
mcov = []
for m in sorted({x["date"][:7] for x in daily}):
    ds = [x for x in daily if x["date"].startswith(m)]
    e = sum(x["expected"] for x in ds)
    def agg(key):
        return round(sum(x[key] * x["expected"] for x in ds) / e, 2)
    mcov.append({"month": m, "expected_slots": e, "A_pct": agg("A_pct"), "B_temp_pct": agg("B_temp_pct"),
                 "B_lux_pct": agg("B_lux_pct"), "B_float_pct": agg("B_float_pct"), "B_all3_pct": agg("B_all3_pct")})
out["monthly_slot_coverage"] = mcov

# ---- gaps ----
gaps = []
for a, b in zip(main, main[1:]):
    g = (b["_t"] - a["_t"]).total_seconds()
    gaps.append((g, a["_t"], b["_t"]))
gaps.sort(reverse=True)
out["top_gaps"] = [{"seconds": round(g, 3), "hours": round(g / 3600, 2), "from": fmt(a), "to": fmt(b)} for g, a, b in gaps[:8]]
iv = sorted(g for g, _, _ in gaps)
out["intervals"] = {"median_s": round(st.median(iv), 3), "lt60_count": sum(x < 60 for x in iv),
                    "gt600_count": sum(x > 600 for x in iv)}

# ---- 9/9 transition rows ----
t0, t1 = jst(2026, 9, 9, 14, 30), jst(2026, 9, 9, 16, 30)
out["sep9_transition_rows"] = [
    {"id": r["id"], "t": fmt(r["_t"]), "solution_temperature": r["solution_temperature"],
     "light_lux": r["light_lux"], "float": r["float_switch_state"], "vitality": r["vitality_score"]}
    for r in main if t0 <= r["_t"] <= t1]
post = [r for r in main if r["_t"] >= jst(2026, 9, 9, 15, 10)]
out["post_sep9"] = {"rows": len(post), "vitality_100_rows": sum(r["vitality_score"] == 100 for r in post),
                    "vitality_values": sorted({r["vitality_score"] for r in post}),
                    "float_states": dict(collections.Counter(r["float_switch_state"] for r in post))}

# ---- C: cloud arrival latency from Outbox ----
ob = list(csv.DictReader(open(DATA / "outbox_timing.csv")))
lat = []
for r in ob:
    m, s = parse_ts(r["measured_at"]), parse_ts(r["synced_at_utc"])
    if m and s:
        lat.append(((s - m).total_seconds(), int(r["retry_count"]), m))
L = sorted(x[0] for x in lat)
q = lambda p: round(L[min(len(L) - 1, int(p * (len(L) - 1) + 0.5))], 3)
mA, mB = min(x[2] for x in lat), max(x[2] for x in lat)
supa_in_range = sum(mA <= r["_t"] <= mB for r in main)
out["C_outbox"] = {
    "rows": len(ob), "synced": sum(r["status"] == "synced" for r in ob),
    "measured_range": [fmt(mA), fmt(mB)], "supabase_main_rows_same_range": supa_in_range,
    "latency_s": {"min": round(L[0], 3), "median": q(.5), "p95": q(.95), "p99": q(.99), "max": round(L[-1], 3)},
    "within_10s": sum(x <= 10 for x in L), "within_60s": sum(x <= 60 for x in L),
    "within_300s": sum(x <= 300 for x in L), "over_300s": sum(x > 300 for x in L),
    "retried_rows": sum(x[1] > 0 for x in lat),
    "retried_latencies_s": sorted(round(x[0], 1) for x in lat if x[1] > 0),
}

# ---- care_logs / observations (C-section support) ----
care = load_jsonl(DATA / "supabase_care_logs.jsonl")
obs = load_jsonl(DATA / "supabase_plant_observations.jsonl")
kinds = collections.Counter()
for c in care:
    note = c["note"] or ""
    kinds["slack_photo" if note.startswith("Slackに植物観察写真") else
          "float_recovery_auto" if note.startswith("自動記録") else
          "test_record" if note.startswith("機能テスト") else "manual_or_other"] += 1
out["care_logs"] = {"rows": len(care), "kinds": dict(kinds), "with_sensor_log_id": sum(bool(c["sensor_log_id"]) for c in care),
                    "range": [fmt(min(parse_ts(c["created_at"]) for c in care)), fmt(max(parse_ts(c["created_at"]) for c in care))]}
out["plant_observations"] = {
    "rows": len(obs), "with_sensor_log_id": sum(bool(o["sensor_log_id"]) for o in obs),
    "by_model": dict(collections.Counter(o["model"] for o in obs)),
    "registration_lag_hours": sorted(round((parse_ts(o["created_at"]) - parse_ts(o["observed_at"])).total_seconds() / 3600, 2) for o in obs)}

write_json("supabase_eval.json", out)
print("main", out["main_rows"], out["main_first"], out["main_last"])
for w in W:
    print(f'{w["window"]}: exp={w["expected_slots"]} A={w["A_record_pct"]}% all3={w["B_all3_valid_pct"]}% T={w["B_temperature_valid_pct"]} L={w["B_light_lux_valid_pct"]} F={w["B_float_valid_pct"]} raw={w["raw_rows_in_window"]}')
print(out["C_outbox"])
print(out["row_level_overall"], out["temperature_last_non_null"], out["light_lux_last_non_null"])
