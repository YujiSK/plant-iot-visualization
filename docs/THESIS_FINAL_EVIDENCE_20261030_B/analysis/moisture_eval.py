#!/usr/bin/env python3
"""Moisture-probe ADC pilot: descriptive statistics, continuity, change points.

Input : ../data/adc_snapshot.csv (fixed read-only snapshot, see export_adc_snapshot.py)
        /home/pi/plant-iot-moisture/initial_pilot_49_samples.csv
Output: ../results/moisture_metrics.json, ../results/moisture_daily.csv,
        ../results/moisture_10min.csv, ../results/moisture_changepoints.csv

ADC raw counts only. No conversion to water content (no calibration exists).
Higher count = higher probe-circuit voltage; in the 49-sample bench check the
probe in open air read ~4091 and in wet filter wool ~3755 (see pilot section).
Times JST unless suffixed _utc.
"""
import csv
import datetime as dt
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
RES = HERE.parent / "results"
JST = dt.timezone(dt.timedelta(hours=9))
FULL_SCALE = 4095
SAT = 4090            # "clipped at ceiling" screening threshold (>= 99.9 % of full scale)
PLATEAU = 4085        # hourly-median plateau threshold (>= 99.76 % of full scale)
SERVICE_START = dt.datetime(2026, 10, 13, 11, 4, 57, 426000, tzinfo=JST)  # systemd ActiveEnterTimestamp / first service row
CUTOFF = dt.datetime(2026, 10, 30, 17, 0, tzinfo=JST)


def desc(v):
    a = np.asarray(v, dtype=float)
    return {
        "n": int(a.size), "min": int(a.min()), "max": int(a.max()),
        "mean": round(float(a.mean()), 2), "median": float(np.median(a)),
        "sd_sample": round(float(a.std(ddof=1)), 2) if a.size > 1 else None,
        "p05": float(np.percentile(a, 5)), "p95": float(np.percentile(a, 95)),
        "ge4090_pct": round(100 * float((a >= SAT).mean()), 2),
    }


def load():
    rows = []
    for r in csv.DictReader(open(DATA / "adc_snapshot.csv")):
        t = dt.datetime.fromisoformat(r["observed_at_utc"]).astimezone(JST)
        rows.append((int(r["id"]), t, None if r["adc_raw"] == "" else int(r["adc_raw"]), r["quality_flag"]))
    return rows


def binseg(y, min_size, penalty, max_cp=12):
    """Binary segmentation, L2 cost (mean shift). Returns sorted split indices."""
    y = np.asarray(y, float)
    cs, cs2 = np.concatenate([[0], np.cumsum(y)]), np.concatenate([[0], np.cumsum(y * y)])

    def cost(a, b):
        n = b - a
        s = cs[b] - cs[a]
        return (cs2[b] - cs2[a]) - s * s / n

    segs, cps = [(0, len(y))], []
    while len(cps) < max_cp:
        best = None
        for a, b in segs:
            if b - a < 2 * min_size:
                continue
            base = cost(a, b)
            for k in range(a + min_size, b - min_size + 1):
                g = base - cost(a, k) - cost(k, b)
                if best is None or g > best[0]:
                    best = (g, k, a, b)
        if best is None or best[0] < penalty:
            break
        g, k, a, b = best
        cps.append((k, g))
        segs.remove((a, b))
        segs += [(a, k), (k, b)]
    return sorted(cps)


def main():
    RES.mkdir(exist_ok=True)
    rows = load()
    out = {"snapshot_rows": len(rows), "cutoff_jst_exclusive": CUTOFF.isoformat()}
    pre = [r for r in rows if r[1] < SERVICE_START]
    svc = [r for r in rows if r[1] >= SERVICE_START]
    out["pre_service_rows"] = [{"id": r[0], "t": r[1].isoformat(), "adc": r[2]} for r in pre]
    vals = [r[2] for r in svc]
    times = [r[1] for r in svc]
    out["first_service_row"] = times[0].isoformat()
    out["last_row"] = times[-1].isoformat()
    out["null_rows"] = sum(v is None for v in vals)
    out["error_flag_rows"] = sum(r[3] == "error" for r in svc)

    # --- continuity: nominal 60 s from service start
    iv = np.diff([t.timestamp() for t in times])
    elapsed = (CUTOFF - SERVICE_START).total_seconds()
    expected_nominal = int(elapsed // 60) + (1 if elapsed % 60 else 0)
    missing_from_gaps = int(sum(max(0, round(x / 60) - 1) for x in iv))
    out["continuity"] = {
        "definition": "expected = ceil((cutoff - service_start)/60 s); missing = sum(round(gap/60)-1) over intervals",
        "expected_nominal_60s": expected_nominal,
        "observed": len(svc),
        "observed_over_expected_pct": round(100 * len(svc) / expected_nominal, 3),
        "missing_from_gaps": missing_from_gaps,
        "interval_s": {"min": round(float(iv.min()), 3), "median": round(float(np.median(iv)), 3),
                       "mean": round(float(iv.mean()), 5), "max": round(float(iv.max()), 3),
                       "gt90": int((iv > 90).sum())},
        "cumulative_drift_s_vs_nominal": round(float((times[-1] - times[0]).total_seconds() - 60 * (len(times) - 1)), 3),
    }

    out["overall"] = desc(vals)

    # --- daily
    by_day = defaultdict(list)
    for t, v in zip(times, vals):
        by_day[t.date().isoformat()].append(v)
    with open(RES / "moisture_daily.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date_jst", "n", "min", "p05", "median", "mean", "p95", "max", "sd", "ge4090_pct", "note"])
        for d in sorted(by_day):
            s = desc(by_day[d])
            note = "partial" if d in ("2026-10-13", "2026-10-30") else ""
            w.writerow([d, s["n"], s["min"], s["p05"], s["median"], s["mean"], s["p95"], s["max"], s["sd_sample"], s["ge4090_pct"], note])
    out["daily"] = {d: desc(v) for d, v in sorted(by_day.items())}

    # --- 10-min medians
    bins = defaultdict(list)
    for t, v in zip(times, vals):
        k = t.replace(minute=t.minute - t.minute % 10, second=0, microsecond=0)
        bins[k].append(v)
    keys = sorted(bins)
    med = [float(np.median(bins[k])) for k in keys]
    with open(RES / "moisture_10min.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bin_start_jst", "n", "median", "min", "max"])
        for k in keys:
            w.writerow([k.isoformat(), len(bins[k]), np.median(bins[k]), min(bins[k]), max(bins[k])])

    # --- sustained ceiling plateau: first hour from which every later hourly median >= PLATEAU
    hb = defaultdict(list)
    for t, v in zip(times, vals):
        hb[t.replace(minute=0, second=0, microsecond=0)].append(v)
    hkeys = sorted(hb)
    hmed = [float(np.median(hb[k])) for k in hkeys]
    onset = None
    for i in range(len(hmed)):
        if all(m >= PLATEAU for m in hmed[i:]):
            onset = hkeys[i]
            break
    out["saturation"] = {
        "plateau_threshold_adc": PLATEAU, "clip_threshold_adc": SAT,
        "definition": "first clock hour from which all later hourly medians >= plateau threshold (JST)",
        "sustained_onset_jst": onset.isoformat() if onset else None,
    }
    if onset:
        pre_sat = [v for t, v in zip(times, vals) if t < onset]
        post_sat = [v for t, v in zip(times, vals) if t >= onset]
        out["saturation"]["before"] = desc(pre_sat)
        out["saturation"]["after"] = desc(post_sat)
        out["saturation"]["after_hours"] = round((CUTOFF - onset).total_seconds() / 3600, 1)
        out["saturation"]["after_value_counts"] = {int(k): int(c) for k, c in zip(*np.unique(post_sat, return_counts=True))}
        out["saturation"]["after_min_hourly_median"] = min(m for k, m in zip(hkeys, hmed) if k >= onset)

    # --- change points on 10-min medians (descriptive candidates, not interventions)
    y = np.array(med)
    noise = float(np.median(np.abs(np.diff(y))) / 0.6745 / np.sqrt(2))  # robust sigma of 10-min medians
    penalty = 2 * np.log(len(y)) * noise ** 2 * 25  # BIC-like, scaled x25 to keep only large shifts
    cps = binseg(y, min_size=6, penalty=penalty)
    cp_rows = []
    for k, gain in cps:
        t_cp = keys[k]
        b = [v for t, v in zip(times, vals) if t_cp - dt.timedelta(minutes=60) <= t < t_cp]
        a = [v for t, v in zip(times, vals) if t_cp <= t < t_cp + dt.timedelta(minutes=60)]
        mb, ma = float(np.median(b)), float(np.median(a))
        # refine to the minute: largest 15-min-median contrast within +-30 min
        best = None
        for t, _ in zip(times, vals):
            if abs((t - t_cp).total_seconds()) > 1800:
                continue
            bb = [v for tt, v in zip(times, vals) if t - dt.timedelta(minutes=15) <= tt < t]
            aa = [v for tt, v in zip(times, vals) if t <= tt < t + dt.timedelta(minutes=15)]
            if bb and aa:
                c = abs(np.median(aa) - np.median(bb))
                if best is None or c > best[0]:
                    best = (c, t)
        cp_rows.append({
            "cp_10min_bin_jst": t_cp.isoformat(), "refined_minute_jst": best[1].isoformat(timespec="seconds"),
            "median_60min_before": mb, "median_60min_after": ma, "delta_adc": ma - mb,
            "delta_pct_of_before": round(100 * (ma - mb) / mb, 2),
            "delta_pct_of_full_scale": round(100 * (ma - mb) / FULL_SCALE, 2),
            "cost_gain": round(float(gain), 1),
        })
    out["changepoints"] = {"method": "binary segmentation, L2 mean-shift, 10-min medians, min segment 60 min",
                           "robust_sigma_10min": round(noise, 2), "penalty": round(float(penalty), 1),
                           "candidates": cp_rows}
    with open(RES / "moisture_changepoints.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cp_rows[0].keys()))
        w.writeheader()
        w.writerows(cp_rows)

    # --- segments between change points: stats + linear slope (ADC/day)
    edges = [SERVICE_START] + [dt.datetime.fromisoformat(c["cp_10min_bin_jst"]) for c in cp_rows] + [CUTOFF]
    segs = []
    for a, b in zip(edges, edges[1:]):
        sv = [(t, v) for t, v in zip(times, vals) if a <= t < b]
        if len(sv) < 2:
            continue
        x = np.array([(t - a).total_seconds() / 86400 for t, _ in sv])
        yv = np.array([v for _, v in sv], float)
        slope = float(np.polyfit(x, yv, 1)[0])
        segs.append({"start": a.isoformat(timespec="seconds"), "end": b.isoformat(timespec="seconds"),
                     "hours": round((b - a).total_seconds() / 3600, 1), **desc(yv), "slope_adc_per_day": round(slope, 1)})
    out["segments"] = segs

    # --- stable windows: 6-h rolling windows (step 1 h), lowest SD, excluding clipped windows
    stable = []
    t0 = SERVICE_START.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
    arr_t = np.array([t.timestamp() for t in times])
    arr_v = np.array(vals, float)
    t = t0
    while t + dt.timedelta(hours=6) <= CUTOFF:
        m = (arr_t >= t.timestamp()) & (arr_t < (t + dt.timedelta(hours=6)).timestamp())
        seg = arr_v[m]
        if seg.size >= 300:
            stable.append((float(seg.std(ddof=1)), float(np.median(seg)), float(seg.max() - seg.min()), t, float((seg >= SAT).mean())))
        t += dt.timedelta(hours=1)
    unclipped = sorted([s for s in stable if s[4] < 0.05], key=lambda s: s[0])
    picked = []
    for s in unclipped:
        if all(abs((s[3] - p[3]).total_seconds()) >= 6 * 3600 for p in picked):
            picked.append(s)
        if len(picked) == 5:
            break
    out["stable_windows_unclipped_6h"] = [
        {"start": s[3].isoformat(timespec="minutes"), "sd": round(s[0], 2), "median": s[1], "range": s[2]} for s in picked]
    out["sd_6h_window_distribution"] = {
        "unclipped_median_sd": round(float(np.median([s[0] for s in unclipped])), 2) if unclipped else None,
        "post_onset_median_sd": round(float(np.median([s[0] for s in stable if onset and s[3] >= onset])), 2) if onset else None,
    }

    # --- hour-of-day profile before saturation (full days 10/14-10/18)
    hod = defaultdict(list)
    for tt, v in zip(times, vals):
        if dt.date(2026, 10, 14) <= tt.date() <= dt.date(2026, 10, 18):
            hod[tt.hour].append(v)
    out["hour_of_day_median_1014_1018"] = {h: float(np.median(hod[h])) for h in sorted(hod)}

    # --- largest 1-min jumps
    d = np.diff(vals)
    idx = np.argsort(-np.abs(d))[:10]
    out["largest_1min_jumps"] = [{"from": times[i].isoformat(timespec="seconds"), "adc_from": vals[i], "adc_to": vals[i + 1]} for i in idx]
    out["abs_1min_diff"] = {"median": float(np.median(np.abs(d))), "p99": float(np.percentile(np.abs(d), 99))}

    # --- initial bench pilot (49 samples)
    groups = defaultdict(list)
    for r in csv.DictReader(open("/home/pi/plant-iot-moisture/initial_pilot_49_samples.csv")):
        groups[r["phase"]].append(int(r["adc_raw"]))
    out["bench_pilot_49"] = {g: desc(v) for g, v in groups.items()}

    (RES / "moisture_metrics.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    show = {k: out[k] for k in ("continuity", "overall", "saturation", "changepoints", "segments",
                                 "stable_windows_unclipped_6h", "sd_6h_window_distribution", "bench_pilot_49")}

    print(json.dumps(show, indent=1, ensure_ascii=False, default=str))
    print("hod:", out["hour_of_day_median_1014_1018"])


if __name__ == "__main__":
    main()
