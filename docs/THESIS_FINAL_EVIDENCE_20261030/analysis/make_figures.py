#!/usr/bin/env python3
"""Figures for THESIS_FINAL_EVIDENCE_20261030 (run after supabase_eval.py and moisture_eval.py)."""
import csv
import datetime as dt
import json

import numpy as np
import matplotlib.dates as mdates

from common import (C_AQUA, C_BLUE, C_MUTED, C_ORANGE, C_YELLOW, DATA, FIG, JST,
                    RESULTS, parse_ts, setup_matplotlib)

plt = setup_matplotlib()
M = json.loads((RESULTS / "moisture_eval.json").read_text())
S = json.loads((RESULTS / "supabase_eval.json").read_text())
TZ = mdates.DateFormatter("%m/%d", tz=JST)

rows = [r for r in csv.reader(open(DATA / "adc_snapshot_raw.csv")) if r[0].isdigit()]
t = [parse_ts(r[1]).astimezone(JST) for r in rows]
a = np.array([int(r[6]) for r in rows])
H = list(csv.DictReader(open(RESULTS / "moisture_hourly.csv")))
ht = [dt.datetime.fromisoformat(h["hour_jst"]) + dt.timedelta(minutes=30) for h in H]
hm = [float(h["median"]) for h in H]
pil = M["initial_pilot"]
open_lo = min(pil["probe_open_before"]["min"], pil["probe_wiped_after"]["min"])


def base_ts(ax, title):
    ax.plot(t, a, color=C_BLUE, lw=0.4, alpha=0.35, label="1分値（生ADC）")
    ax.plot(ht, hm, color=C_BLUE, lw=1.8, label="1時間中央値")
    ax.axhline(4095, color=C_MUTED, lw=1, ls="--")
    ax.text(t[-1], 4097, "12bit上限 4095", ha="right", va="bottom", fontsize=8, color="#52514e")
    ax.axhspan(open_lo, 4095, color=C_YELLOW, alpha=0.12, lw=0)
    ax.text(t[0] + dt.timedelta(hours=6), open_lo - 8, f"初期手動試験の開放・拭取時の範囲（ADC {open_lo}～4095）",
            fontsize=8, va="top", color="#52514e")
    ax.set_ylabel("ADC値（12bit、未校正）")
    ax.xaxis.set_major_formatter(TZ)
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_ylim(3080, 4130)


# M1: full time series
fig, ax = plt.subplots(figsize=(10, 4.2))
base_ts(ax, "図M1 水分プローブADC値の時系列（raspi2 MCP3204 CH0、60秒周期、2026/10/13 11:04～10/30 17:53 JST）")
ev = parse_ts(M["events"][0]["t"])
ax.axvline(ev, color=C_ORANGE, lw=1.2)
ax.text(ev, 3100, " 記録開始注記（唯一の記録イベント）", color="#0b0b0b", fontsize=8, va="bottom")
ax.legend(loc="lower right", fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(FIG / "M1_adc_timeseries.png"); plt.close(fig)

# M2: change-point candidates + segment medians (no recorded condition changes)
fig, ax = plt.subplots(figsize=(10, 4.4))
base_ts(ax, "図M2 統計的変化点候補と区間中央値（条件変更の記録時刻は存在しない）")
for s in M["segments"]:
    s0, s1 = dt.datetime.fromisoformat(s["start"]), dt.datetime.fromisoformat(s["end_exclusive"])
    ax.hlines(s["median"], s0, s1, color=C_ORANGE, lw=2.2)
major = [c for c in M["change_point_candidates"] if c["gain"] >= 5000]
for c in major:
    x = dt.datetime.fromisoformat(c["hour"])
    ax.axvline(x, color=C_ORANGE, lw=0.9, ls=":")
    ax.text(x, 3120, x.strftime(" %m/%d %H時"), rotation=90, fontsize=7, va="bottom", color="#52514e")
ax.plot([], [], color=C_ORANGE, lw=2.2, label="区間中央値（二分割法・L2）")
ax.plot([], [], color=C_ORANGE, lw=0.9, ls=":", label="変化点候補（介入時刻ではない）")
ax.legend(loc="lower right", fontsize=8, frameon=False)
fig.tight_layout(); fig.savefig(FIG / "M2_adc_changepoints.png"); plt.close(fig)

# M3: daily median with range, and daily share >=4094 (small multiples, shared x)
D = M["daily"]
dd = [dt.datetime.fromisoformat(x["date"]).replace(hour=12, tzinfo=JST) for x in D]
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.4), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
ax1.vlines(dd, [x["min"] for x in D], [x["max"] for x in D], color=C_BLUE, lw=2, alpha=0.35)
ax1.plot(dd, [x["median"] for x in D], "o-", color=C_BLUE, ms=5, lw=1.4)
ax1.set_ylabel("ADC（日中央値と最小～最大）")
ax1.set_title("図M3 日別ADC分布（上）と上限近傍値（≥4094）の割合（下）、JST暦日", loc="left", fontsize=11)
ax2.bar(dd, [x["ge4094_pct"] for x in D], width=0.7, color=C_AQUA)
ax2.set_ylabel("ADC≥4094の割合（%）"); ax2.set_ylim(0, 100)
ax2.xaxis.set_major_formatter(TZ)
fig.tight_layout(); fig.savefig(FIG / "M3_adc_daily.png"); plt.close(fig)

# M4: initial pilot comparison (only recorded condition comparison)
fig, ax = plt.subplots(figsize=(7, 3.8))
labels = {"probe_open_before": "開放（挿入前）", "wet_filter_wool": "湿潤ろ過ウールに接触", "probe_wiped_after": "拭取後（開放）"}
pr = list(csv.DictReader(open(DATA / "initial_pilot_49_samples.csv")))
for i, (k, lab) in enumerate(labels.items()):
    v = [int(r["adc_raw"]) for r in pr if r["phase"] == k]
    x = i + (np.random.default_rng(0).random(len(v)) - 0.5) * 0.25
    ax.scatter(x, v, s=22, color=[C_MUTED, C_BLUE, C_MUTED][i], edgecolor="#fcfcfb", lw=0.8, zorder=3)
    ax.hlines(np.median(v), i - 0.25, i + 0.25, color="#0b0b0b", lw=2)
    ax.text(i + 0.28, np.median(v), f"中央値{np.median(v):.0f}\nn={len(v)}", va="center", fontsize=8)
ax.set_xticks(range(3)); ax.set_xticklabels(labels.values())
ax.set_ylabel("ADC値（未校正）")
ax.set_title("図M4 初期手動試験（10/13、49標本、反復なし）", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig(FIG / "M4_initial_pilot.png"); plt.close(fig)

# S1/S2: Supabase daily coverage
C = list(csv.DictReader(open(RESULTS / "supabase_daily_coverage.csv")))
cd = [dt.datetime.fromisoformat(x["date"]).replace(hour=12, tzinfo=JST) for x in C]
f = lambda k: [float(x[k]) for x in C]
fig, ax = plt.subplots(figsize=(10, 3.8))
ax.plot(cd, f("A_pct"), color=C_BLUE, lw=1.6, label="A 記録が存在する5分枠")
ax.plot(cd, f("B_all3_pct"), color=C_ORANGE, lw=1.6, label="B 3センサーとも有効値の5分枠")
ax.set_ylim(-3, 105); ax.set_ylabel("日別取得率（%）")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d", tz=JST))
for x, lab in [(dt.datetime(2026, 7, 11, 15, 40, tzinfo=JST), "認証障害"), (dt.datetime(2026, 8, 2, 19, 16, tzinfo=JST), "転倒・途絶"),
               (dt.datetime(2026, 9, 9, 15, 10, tzinfo=JST), "温度・照度欠損開始")]:
    ax.axvline(x, color=C_MUTED, lw=0.8, ls=":"); ax.text(x, 50, " " + lab, fontsize=8, color="#52514e")
ax.legend(loc="lower left", fontsize=8, frameon=False)
ax.set_title("図S1 Supabase主要系列の日別5分枠取得率：記録存在(A)と有効測定(B)（JST、±150秒最近傍）", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig(FIG / "S1_supabase_daily_A_vs_B.png"); plt.close(fig)

fig, axs = plt.subplots(3, 1, figsize=(10, 5.6), sharex=True)
for ax, (k, lab, c) in zip(axs, [("B_temp_pct", "養液温度 DS18B20", C_BLUE), ("B_lux_pct", "照度 BH1750", C_AQUA), ("B_float_pct", "フロートスイッチ", C_YELLOW)]):
    ax.fill_between(cd, f(k), color=c, alpha=0.25, lw=0); ax.plot(cd, f(k), color=c, lw=1.3)
    ax.set_ylim(0, 105); ax.text(0.005, 0.12, lab, transform=ax.transAxes, fontsize=9)
axs[1].set_ylabel("有効値のある5分枠（%）")
axs[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d", tz=JST))
axs[0].set_title("図S2 センサー別の日別有効値取得率（温度は0～50℃、照度は非NULL・≥0）", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig(FIG / "S2_supabase_sensor_validity.png"); plt.close(fig)

# S3: Outbox cloud-arrival latency
ob = list(csv.DictReader(open(DATA / "outbox_timing.csv")))
lat = np.array([(parse_ts(r["synced_at_utc"]) - parse_ts(r["measured_at"])).total_seconds() for r in ob])
retry = np.array([int(r["retry_count"]) > 0 for r in ob])
fig, ax = plt.subplots(figsize=(8, 3.6))
bins = np.logspace(np.log10(0.1), np.log10(400), 50)
ax.hist(lat[~retry], bins=bins, color=C_BLUE, label=f"初回送信で同期（n={(~retry).sum()}）")
ax.hist(lat[retry], bins=bins, color=C_ORANGE, label=f"再試行後に同期（n={retry.sum()}）")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("測定時刻→Supabase同期完了までの時間（秒、対数）"); ax.set_ylabel("件数（対数）")
ax.legend(fontsize=8, frameon=False)
ax.set_title("図S3 クラウド到達遅延（Outbox保持分 2026/9/13～10/13）", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig(FIG / "S3_outbox_latency.png"); plt.close(fig)
print(sorted(p.name for p in FIG.iterdir()))
