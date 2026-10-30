"""Shared helpers for THESIS_FINAL_EVIDENCE_20261030 analyses.

All reported times are JST (Asia/Tokyo, UTC+09:00, no DST). Inputs are the
read-only snapshots under ../data/ (see data/SHA256SUMS).
"""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIG = ROOT / "figures"
RESULTS = ROOT / "results"
JST = dt.timezone(dt.timedelta(hours=9))

MAIN_DEVICE = "raspberrypi2"
MAIN_SOURCE = "raspberrypi2-ds18b20-bh1750-float"


def parse_ts(s):
    """ISO8601 -> aware datetime. SQLite CURRENT_TIMESTAMP strings are UTC."""
    if s is None:
        return None
    s = s.replace(" ", "T")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t


def jst(y, m, d, hh=0, mm=0, ss=0):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=JST)


def fmt(t):
    return t.astimezone(JST).isoformat(timespec="seconds") if t else None


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def write_json(name, obj):
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def setup_matplotlib():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for p in ["/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"]:
        if Path(p).exists():
            font_manager.fontManager.addfont(p)
            # DejaVu for Latin/symbols, per-glyph fallback to the CJK font
            plt.rcParams["font.family"] = ["DejaVu Sans", font_manager.FontProperties(fname=p).get_name()]
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 150, "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.color": "#e4e3df",
        "grid.linewidth": 0.6, "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b",
        "xtick.color": "#52514e", "ytick.color": "#52514e", "lines.linewidth": 1.6,
        "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    })
    FIG.mkdir(exist_ok=True)
    return plt


# Reference categorical palette (dataviz skill, light mode), fixed order.
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
C_MUTED = "#8a8984"
