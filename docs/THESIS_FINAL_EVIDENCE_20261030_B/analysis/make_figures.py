#!/usr/bin/env python3
"""Render thesis figures (PNG) from ../data and ../results.

Requires matplotlib (run with an isolated venv, e.g.
  python3 -m venv --system-site-packages /tmp/venv && /tmp/venv/bin/pip install matplotlib
  /tmp/venv/bin/python make_figures.py)
"""
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

HERE = Path(__file__).resolve().parent
DATA, RES, FIG = HERE.parent / "data", HERE.parent / "results", HERE.parent / "figures"
FIG.mkdir(exist_ok=True)
JST = dt.timezone(dt.timedelta(hours=9))

# --- style: reference palette slots 1-3, recessive grid, thin marks
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
for f in ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",):
    font_manager.fontManager.addfont(f)
plt.rcParams.update({
    "font.family": ["DejaVu Sans", "Droid Sans Fallback"], "font.size": 9,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "legend.frameon": False, "figure.dpi": 150, "savefig.bbox": "tight",
})
TZ = mdates.ConciseDateFormatter(mdates.AutoDateLocator(tz=JST), tz=JST)


def jst(s):
    return dt.datetime.fromisoformat(s).astimezone(JST)


def save(fig, name):
    fig.savefig(FIG / name, facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ======================= moisture ADC
adc = [(jst(r["observed_at_utc"]), int(r["adc_raw"])) for r in csv.DictReader(open(DATA / "adc_snapshot.csv"))]
mm = json.load(open(RES / "moisture_metrics.json"))
t = np.array([a for a, _ in adc])
v = np.array([b for _, b in adc])
hb = defaultdict(list)
for a, b in adc:
    hb[a.replace(minute=0, second=0, microsecond=0)].append(b)
ht = sorted(hb)
hm = [np.median(hb[k]) for k in ht]
onset = jst(mm["saturation"]["sustained_onset_jst"])
start_evt = jst("2026-10-13T02:04:28.735+00:00")
bench = mm["bench_pilot_49"]
key_cps = ["2026-10-16T11:36:57+09:00", "2026-10-18T21:06:58+09:00"]


def bench_bands(ax, label=True):
    o = bench["probe_open_before"]
    w = bench["wet_filter_wool"]
    ax.axhspan(o["min"], 4095, color=MUTED, alpha=0.12, lw=0)
    ax.axhspan(w["min"], w["max"], color=AQUA, alpha=0.15, lw=0)
    if label:
        ax.text(1.005, (o["min"] + 4095) / 2, "台上試験: 空気中\n(open, n=11)", transform=ax.get_yaxis_transform(),
                va="center", fontsize=7, color=INK2)
        ax.text(1.005, (w["min"] + w["max"]) / 2, "台上試験: 湿潤ろ過ウール\n(n=19)", transform=ax.get_yaxis_transform(),
                va="center", fontsize=7, color=INK2)


# Fig 1: full time series
fig, ax = plt.subplots(figsize=(10, 4.2))
bench_bands(ax)
ax.plot(t, v, color=BLUE, lw=0.4, alpha=0.35, label="1分値（生ADC）")
ax.plot(ht, hm, color=BLUE, lw=1.6, label="1時間中央値")
ax.axvspan(onset, t[-1], color=ORANGE, alpha=0.08, lw=0)
ax.axvline(start_evt, color=INK2, lw=1, ls="-")
ax.annotate("記録済みイベント (唯一)\n10/13 11:04 開始注記", (start_evt, 3150), xytext=(8, 0), textcoords="offset points",
            fontsize=7, color=INK2, va="bottom")
ax.annotate(f"上限張り付き (時間中央値≥4085)\n{onset:%m/%d %H:%M}〜 {mm['saturation']['after_hours']:.0f} h",
            (onset, 3400), xytext=(8, 0), textcoords="offset points", fontsize=7, color=INK2)
ax.set_ylim(3080, 4130)
ax.set_ylabel("ADC raw (12-bit, 0–4095)")
ax.set_title("図1 水分プローブ未校正ADC値の時系列（2026-10-13 11:04 〜 10-30 17:00 JST, n=24,836）")
ax.xaxis.set_major_formatter(TZ)
ax.legend(loc="lower right", fontsize=8)
save(fig, "fig1_adc_timeseries.png")

# Fig 2: change-point candidates vs documented events (first 6.5 days)
fig, ax = plt.subplots(figsize=(10, 4.2))
bench_bands(ax, label=False)
lim = jst("2026-10-20T00:00:00+09:00")
m = t < lim
ax.plot(t[m], v[m], color=BLUE, lw=0.4, alpha=0.35, label="1分値")
hm_arr = np.array(hm)
hmask = np.array([k < lim for k in ht])
ax.plot(np.array(ht)[hmask], hm_arr[hmask], color=BLUE, lw=1.6, label="1時間中央値")
ax.axvline(start_evt, color=INK2, lw=1)
ax.text(start_evt, 4118, " 記録済み: 開始", fontsize=7, color=INK2, va="bottom")
for c, yl, ha in zip(key_cps + [onset.isoformat()], (3300, 3300, 3450), ("left", "right", "left")):
    ct = jst(c)
    ax.axvline(ct, color=ORANGE, lw=1, ls="--")
    ax.text(ct, yl, f" 候補 {ct:%m/%d %H:%M} " , fontsize=7, color=INK2, ha=ha,
            bbox=dict(facecolor="white", edgecolor="none", pad=1))
ax.set_ylim(3080, 4130)
ax.set_ylabel("ADC raw")
ax.set_title("図2 記録済みイベントと統計的変化点候補（橙破線＝介入記録なし・原因未確認）", pad=16)
ax.xaxis.set_major_formatter(TZ)
ax.legend(loc="lower right", fontsize=8)
save(fig, "fig2_adc_events_changepoints.png")

# Fig 3: daily distribution
daily = list(csv.DictReader(open(RES / "moisture_daily.csv")))
by_day = defaultdict(list)
for a, b in adc:
    by_day[a.date().isoformat()].append(b)
days = sorted(by_day)
fig, ax = plt.subplots(figsize=(10, 3.8))
bp = ax.boxplot([by_day[d] for d in days], widths=0.55, showfliers=False, patch_artist=True,
                medianprops=dict(color=INK, lw=1.2), whiskerprops=dict(color=MUTED), capprops=dict(color=MUTED))
for b in bp["boxes"]:
    b.set(facecolor=BLUE, alpha=0.35, edgecolor=BLUE)
ax.set_xticks(range(1, len(days) + 1), [d[5:] + ("*" if d in ("2026-10-13", "2026-10-30") else "") for d in days], fontsize=7)
ax.axhline(4095, color=MUTED, lw=0.8, ls=":")
ax.text(len(days) + 0.6, 4095, "full scale 4095", fontsize=7, color=INK2, va="center")
ax.set_ylabel("ADC raw")
ax.set_ylim(3880, 4110)
ax.set_title("図3 日別ADC分布（箱=四分位, ひげ=1.5IQR, 外れ値非表示; *=部分日; 10/13は下限3,118まで外れ値あり）")
save(fig, "fig3_adc_daily_box.png")

# Fig 4: bench pilot condition comparison (only comparable condition data)
groups = defaultdict(list)
for r in csv.DictReader(open("/home/pi/plant-iot-moisture/initial_pilot_49_samples.csv")):
    groups[r["phase"]].append(int(r["adc_raw"]))
order = [("probe_open_before", "空気中(前)\nn=11"), ("wet_filter_wool", "湿潤ろ過ウール\nn=19"), ("probe_wiped_after", "拭取り後(空気中)\nn=19")]
fig, ax = plt.subplots(figsize=(6, 3.6))
rng = np.random.default_rng(0)
for i, (k, lab) in enumerate(order, 1):
    y = groups[k]
    ax.scatter(i + rng.uniform(-0.12, 0.12, len(y)), y, s=14, color=[BLUE, AQUA, BLUE][i - 1], alpha=0.8, edgecolor="white", lw=0.5)
    ax.hlines(np.median(y), i - 0.25, i + 0.25, color=INK, lw=1.4)
    ax.text(i + 0.28, np.median(y), f"中央値 {np.median(y):.0f}", fontsize=7, color=INK2, va="center")
ax.set_xticks([1, 2, 3], [lab for _, lab in order])
ax.set_xlim(0.5, 3.9)
ax.set_ylabel("ADC raw")
ax.set_title("図4 台上予備試験 49標本（同一プローブ, 単回, 時刻概算）")
save(fig, "fig4_bench_pilot_conditions.png")

# ======================= Supabase
sd = list(csv.DictReader(open(RES / "supabase_daily.csv")))
dd = [dt.datetime.fromisoformat(r["date_jst"]).replace(tzinfo=JST) + dt.timedelta(hours=12) for r in sd]
A = [float(r["A_record_pct"]) for r in sd]
B = [float(r["B_all3_valid_pct"]) for r in sd]
fig, ax = plt.subplots(figsize=(10, 3.8))
ax.step(dd, B, where="mid", color=ORANGE, lw=3.2, label="B: 養液温度・照度・フロートが全て有効な枠の割合", zorder=2)
ax.step(dd, A, where="mid", color=BLUE, lw=1.2, label="A: 記録が存在する5分枠の割合（B と重なる区間は重ね描き）", zorder=3)
for a, b, lab in (("2026-07-11T15:40", "2026-07-22T12:39", "クラウド空白\n(認証障害の記録)"),
                  ("2026-08-02T19:16", "2026-08-07T17:02", "転倒・途絶"),
                  ("2026-09-09T15:10", "2026-10-13T10:35", "温度・照度NULL\n(記録は継続)")):
    a, b = dt.datetime.fromisoformat(a).replace(tzinfo=JST), dt.datetime.fromisoformat(b).replace(tzinfo=JST)
    ax.axvspan(a, b, color=MUTED, alpha=0.12, lw=0)
    ax.text(a + (b - a) / 2, 50, lab, ha="center", va="center", fontsize=7, color=INK2)
ax.set_ylim(-3, 108)
ax.set_ylabel("日別 5分枠充足率 (%)")
ax.set_title("図5 Supabase主要系列：記録の存在(A)と有効測定(B)の乖離（JST日別, 2026-06-13〜10-13）")
ax.xaxis.set_major_formatter(TZ)
ax.legend(loc="lower left", fontsize=8)
save(fig, "fig5_supabase_daily_A_vs_B.png")

# Fig 6: period bars
sm = json.load(open(RES / "supabase_metrics.json"))["coverage"]
periods = [("P1 initial [6/13 01:20,7/11 15:45)", "P1\n6/13–7/11"),
           ("formal_post_recovery [7/22 13:05,8/2 19:15] inclusive", "P2\n7/22 13:05–8/2"),
           ("P3 post-accident [8/7 17:05,9/9 15:10)", "P3\n8/7–9/9"),
           ("P4 sensors-null [9/9 15:10,10/13 10:40)", "P4\n9/9–10/13"),
           ("full_record_span [6/13 01:20,10/13 10:40)", "全期間\n6/13–10/13")]
fig, ax = plt.subplots(figsize=(8, 3.6))
x = np.arange(len(periods))
wdt = 0.36
a_vals = [sm[k]["A_record_pct"] for k, _ in periods]
b_vals = [sm[k]["B_all3_valid_pct"] for k, _ in periods]
ax.bar(x - wdt / 2 - 0.01, a_vals, wdt, color=BLUE, label="A: 記録存在", edgecolor="white", linewidth=1)
ax.bar(x + wdt / 2 + 0.01, b_vals, wdt, color=ORANGE, label="B: 3項目有効", edgecolor="white", linewidth=1)
for i, (a, b) in enumerate(zip(a_vals, b_vals)):
    ax.text(i - wdt / 2, a + 1.5, f"{a:.2f}", ha="center", fontsize=7, color=INK)
    ax.text(i + wdt / 2, b + 1.5, f"{b:.2f}", ha="center", fontsize=7, color=INK)
ax.set_xticks(x, [l for _, l in periods], fontsize=8)
ax.set_ylim(0, 112)
ax.set_ylabel("5分枠充足率 (%)")
ax.set_title("図6 期間別の記録率(A)と有効測定率(B)")
ax.legend(loc="upper center", ncol=2, fontsize=8, bbox_to_anchor=(0.5, -0.22))
save(fig, "fig6_supabase_period_A_vs_B.png")

# Fig 7: cloud arrival latency ECDF (C)
lat = np.sort(np.loadtxt(RES / "outbox_latency_s.csv", skiprows=1))
fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.step(lat, np.arange(1, len(lat) + 1) / len(lat) * 100, where="post", color=BLUE, lw=1.6)
ax.set_xscale("log")
ax.axvline(5, color=MUTED, lw=0.8, ls=":")
ax.text(5.3, 40, f"≤5 s: {np.mean(lat <= 5) * 100:.2f}%", fontsize=7, color=INK2)
ax.text(np.median(lat), 52, f" 中央値 {np.median(lat):.2f} s", fontsize=7, color=INK2)
ax.set_xlabel("Outbox登録→Supabase同期完了 (s, log)")
ax.set_ylabel("累積割合 (%)")
ax.set_title(f"図7 クラウド到達遅延 (C) の累積分布（9/13–10/13, n={len(lat):,}）")
save(fig, "fig7_cloud_latency_ecdf.png")
