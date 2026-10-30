#!/usr/bin/env python3
"""Moisture-probe ADC experiment analysis (raspi2 readings.sqlite3 snapshot).

- Values are raw 12-bit ADC counts of a resistive 2-electrode probe in a
  10 kOhm divider (README). NOT converted to water content (no calibration).
- Continuous segment = rows after the service start (id>=2); id=1 is a manual
  pre-start sample (28.8 s before the service started).
- Expected samples: nominal 60 s grid anchored at the first continuous row;
  each row assigned to nearest grid point (tolerance +-30 s).
- Change-point candidates: binary segmentation on hourly medians with an L2
  cost and a BIC-like penalty; they are statistical candidates, not
  intervention times.
"""
import collections
import csv
import datetime as dt
import statistics as st

import numpy as np

from common import DATA, JST, fmt, parse_ts, write_json, RESULTS

rows, events, snapshot = [], [], None
with open(DATA / "adc_snapshot_raw.csv") as f:
    for rec in csv.reader(f):
        if rec[0] == "# snapshot_utc":
            snapshot = parse_ts(rec[1])
        elif rec[0] == "#event":
            events.append({"id": int(rec[1]), "t": fmt(parse_ts(rec[2])), "note": rec[3]})
        elif rec[0].isdigit():
            rows.append({"id": int(rec[0]), "t": parse_ts(rec[1]), "adc": int(rec[6]) if rec[6] else None,
                         "flag": rec[9], "phase": rec[11]})
out = {"snapshot_extracted_at": fmt(snapshot), "rows_total": len(rows), "events": events,
       "first": fmt(rows[0]["t"]), "last": fmt(rows[-1]["t"]),
       "null_adc": sum(r["adc"] is None for r in rows),
       "flags": dict(collections.Counter(r["flag"] for r in rows)),
       "phases": dict(collections.Counter(r["phase"] for r in rows))}
cont = [r for r in rows if r["id"] >= 2]
t0 = cont[0]["t"]
ts = np.array([(r["t"] - t0).total_seconds() for r in cont])
adc = np.array([r["adc"] for r in cont], dtype=float)
iv = np.diff(ts)
n_exp = int(round(ts[-1] / 60.0)) + 1
grid = np.round(ts / 60.0).astype(int)
out["continuous"] = {
    "start": fmt(t0), "end": fmt(cont[-1]["t"]), "rows": len(cont), "expected_60s_slots": n_exp,
    "filled_slots": int(len(set(grid.tolist()))), "duplicate_slots": int(len(grid) - len(set(grid.tolist()))),
    "missing_slots": int(n_exp - len(set(grid.tolist()))),
    "completeness_pct": round(100 * len(set(grid.tolist())) / n_exp, 3),
    "interval_s": {"min": round(float(iv.min()), 3), "median": round(float(np.median(iv)), 3),
                   "max": round(float(iv.max()), 3), "gt90": int((iv > 90).sum())},
    "cumulative_drift_s": round(float(ts[-1] - 60 * (len(cont) - 1)), 3),
}


def stats(a):
    a = np.asarray(a, dtype=float)
    return {"n": int(a.size), "min": int(a.min()), "max": int(a.max()), "mean": round(float(a.mean()), 2),
            "median": float(np.median(a)), "sd_sample": round(float(a.std(ddof=1)), 2) if a.size > 1 else None,
            "p05": float(np.percentile(a, 5)), "p95": float(np.percentile(a, 95)),
            "ge4094_pct": round(100 * float((a >= 4094).mean()), 2), "eq4095_pct": round(100 * float((a == 4095).mean()), 2)}


out["stats_all_rows"] = stats([r["adc"] for r in rows])
out["stats_continuous"] = stats(adc)

# daily (JST) table
byday = collections.defaultdict(list)
for r in rows:
    byday[r["t"].astimezone(JST).date().isoformat()].append(r["adc"])
daily = [{"date": d, **stats(v)} for d, v in sorted(byday.items())]
with open(RESULTS / "moisture_daily.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
out["daily"] = daily

# hourly medians (JST hour bins) for change-point and stability
hour = collections.defaultdict(list)
for r in cont:
    hour[r["t"].astimezone(JST).replace(minute=0, second=0, microsecond=0)].append(r["adc"])
hk = sorted(hour)
hmed = np.array([np.median(hour[h]) for h in hk])
with open(RESULTS / "moisture_hourly.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["hour_jst", "n", "median", "min", "max"])
    for h in hk:
        w.writerow([h.isoformat(), len(hour[h]), float(np.median(hour[h])), min(hour[h]), max(hour[h])])


def binseg(y, min_size=12, max_cp=8):
    """Binary segmentation, L2 cost, penalty = 2*var*log(n) (var from MAD of diffs)."""
    n = len(y)
    sigma = 1.4826 * np.median(np.abs(np.diff(y) - np.median(np.diff(y)))) / np.sqrt(2)
    pen = 2 * max(sigma, 1.0) ** 2 * np.log(n)
    cs, cs2 = np.concatenate([[0], np.cumsum(y)]), np.concatenate([[0], np.cumsum(y * y)])
    cost = lambda a, b: (cs2[b] - cs2[a]) - (cs[b] - cs[a]) ** 2 / (b - a)
    segs, cps = [(0, n)], []
    while len(cps) < max_cp:
        best = None
        for a, b in segs:
            for k in range(a + min_size, b - min_size + 1):
                gain = cost(a, b) - cost(a, k) - cost(k, b)
                if best is None or gain > best[0]:
                    best = (gain, a, b, k)
        if best is None or best[0] < pen:
            break
        _, a, b, k = best
        segs.remove((a, b)); segs += [(a, k), (k, b)]; cps.append((k, best[0]))
    return sorted(cps), pen


cps, pen = binseg(hmed)
bounds = [0] + [k for k, _ in cps] + [len(hmed)]
segments = []
for a, b in zip(bounds, bounds[1:]):
    seg_rows = [x for h in hk[a:b] for x in hour[h]]
    segments.append({"start": fmt(hk[a]), "end_exclusive": fmt(hk[b - 1] + dt.timedelta(hours=1)),
                     "hours": b - a, **stats(seg_rows)})
out["change_point_method"] = {"input": "hourly medians of continuous rows", "cost": "L2", "min_segment_h": 12,
                              "penalty": round(float(pen), 1), "note": "statistical candidates only"}
out["change_point_candidates"] = [{"hour": fmt(hk[k]), "gain": round(float(g), 1)} for k, g in cps]
out["segments"] = segments
for i in range(1, len(segments)):
    p, c = segments[i - 1]["median"], segments[i]["median"]
    segments[i]["median_change_vs_prev"] = c - p
    segments[i]["median_change_pct_vs_prev"] = round(100 * (c - p) / p, 2)

# most stable 24 h windows (rolling SD of hourly medians, step 1 h), non-saturated vs any
roll = []
for i in range(0, len(hk) - 24 + 1):
    v = [x for h in hk[i:i + 24] for x in hour[h]]
    roll.append((float(np.std(v, ddof=1)), hk[i], float(np.median(v)), round(100 * float((np.array(v) >= 4094).mean()), 1)))
roll.sort()
picked = []
for sd, h, med, sat in roll:
    if all(abs((h - p[1]).total_seconds()) >= 24 * 3600 for p in picked):
        picked.append((sd, h, med, sat))
    if len(picked) == 3:
        break
out["most_stable_24h_windows"] = [{"start": fmt(h), "sd": round(sd, 2), "median": med, "ge4094_pct": sat} for sd, h, med, sat in picked]
nonsat = [x for x in roll if x[3] < 1.0]
out["most_stable_24h_nonsaturated"] = ({"start": fmt(nonsat[0][1]), "sd": round(nonsat[0][0], 2), "median": nonsat[0][2],
                                        "ge4094_pct": nonsat[0][3]} if nonsat else None)

# largest 1-step jumps
d = np.diff(adc)
idx = np.argsort(-np.abs(d))[:10]
out["largest_steps"] = [{"from": fmt(cont[i]["t"]), "to": fmt(cont[i + 1]["t"]), "adc_from": int(adc[i]),
                         "adc_to": int(adc[i + 1]), "delta": int(d[i])} for i in sorted(idx)]
# first time saturation (>=4094) persisted for a full JST day
out["first_day_ge4094_over_50pct"] = next((x["date"] for x in daily if x["ge4094_pct"] > 50), None)

# diurnal amplitude: per day, max-min of hourly medians
amp = collections.defaultdict(list)
for h, m in zip(hk, hmed):
    amp[h.date().isoformat()].append(m)
out["daily_hourly_median_range"] = {k: float(max(v) - min(v)) for k, v in sorted(amp.items())}

# initial 49-sample pilot (separate manual test)
pil = collections.defaultdict(list)
for r in csv.DictReader(open(DATA / "initial_pilot_49_samples.csv")):
    pil[r["phase"]].append(int(r["adc_raw"]))
out["initial_pilot"] = {k: stats(v) for k, v in pil.items()}

write_json("moisture_eval.json", out)
for k in ["snapshot_extracted_at", "rows_total", "first", "last", "null_adc", "flags", "continuous", "stats_continuous"]:
    print(k, out[k])
print("CP", out["change_point_candidates"])
for s in segments:
    print(s["start"], s["end_exclusive"], s["hours"], s["median"], s["mean"], s["sd_sample"], s["ge4094_pct"], s.get("median_change_vs_prev"))
print("stable", out["most_stable_24h_windows"], out["most_stable_24h_nonsaturated"])
print("pilot", {k: (v["n"], v["median"]) for k, v in out["initial_pilot"].items()})
print("sat day", out["first_day_ge4094_over_50pct"])
