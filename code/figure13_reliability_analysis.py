"""Figure 13: inter-rater reliability by capacity and moment. Gwet's AC2 with the raw agreement beneath it.

One PNG. Each cell shows, in bold, Gwet's AC2 (ordinal weights, chance term over the full 1-5 scale) and,
beneath it, "PA% (SD)":
- PA, percent agreement: the share of units on which all the evaluators who rated it gave the same level
  (agreements / units coded). With two evaluators this is the classic two-coder percent agreement; with more
  it counts only perfect agreement, so it is lower than the pairwise agreement of data_reliability_analysis.py
  (the reliability table's 'agreement', the mean share of agreeing rater pairs), which is printed alongside
  for comparison but not drawn.
- SD, mean standard deviation of the scores: for each unit, the sample standard deviation (ddof = 1) of the
  levels the evaluators gave, on the rubric's 1-5 scale; then the mean over the units. Units in perfect
  agreement count with SD 0. It shows how far apart the scores are beyond whether they match exactly.
Both use the units rated by at least two evaluators. The cell colour follows AC2 only.

The grid has one column per capacity plus 'All capacities' (the seven pooled, set apart) and four rows (ROWS):
    Pre-workshop                  human evaluators (H1 ...), pre-workshop interviews
    Post-workshop                 human evaluators, post-workshop interviews
    Both                          human evaluators, all interviews
    Both, incl. LLM scoring       human evaluators and LLM agents (A1 ...) pooled as raters, all interviews
The last row is set apart: it measures agreement in the mixed panel, so it shows whether adding the agents
raises or lowers the agreement of the humans alone (the row above it). The rater groups are those of
data_reliability_analysis.py (GROUPS). Evaluators without a single rating in a cell's scope are left out,
and one who rated only part of the interviews adds only those. A unit is one interview x one capacity;
only units rated by at least two evaluators count.

AC2 is computed by gwet_ac2() of data_reliability_analysis.py, so the 'All capacities' cells of the two
'Both' rows equal the reliability table's gwet_ac2_ordinal for 'Humans' and 'All evaluators'. PA and SD are
computed here (percent_agreement(), mean_score_sd()); the reliability table has neither.

Colours: Altman's (1991) scale with bounds and names from irrCAC (Benchmark.altman()), its five bands in the
five LEVELS colours of plot_shared_config.py (poor grey ... very good blue). A value on a
bound belongs to the higher band, as in irrCAC. The band is read from the point estimate, not from irrCAC's
probabilistic benchmarking (which needs the standard error), so a colour always matches its value. AC2 is
truncated toward zero to three decimals so it never contradicts the colour.

An undefined AC2 (no unit with two ratings, or no variation at all) is drawn as a grey cell with a dash.

Input: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one unless --date
is given. Output: results/figures/figure13_reliability_analysis_YYYYMMDD.png (PNG only, 16 x 6.6 cm, 300 dpi). No title or
caption is drawn (they go in the manuscript); the values and the caption are printed to the console.

Usage (from data_analysis/):
    python code/figure13_reliability_analysis.py
    python code/figure13_reliability_analysis.py --date 20261106
"""
import argparse
import colorsys
import io
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from irrCAC.benchmark import Benchmark
from matplotlib.colors import to_hex, to_rgb
from matplotlib.patches import Patch

from data_reliability_analysis import GROUPS, count_matrix, gwet_ac2, raw_agreement
from plot_shared_config import (
    CAPACITIES, INK, LEVELS, MUTED, OUT_DIR, STAGES, TIME, VERTICAL_SHEET, evaluator_columns, label_ink, latest_summary,
)

GLOBAL = "all"  # key of the pooled column
COLUMNS = [*CAPACITIES, GLOBAL]
COLUMN_LABELS = [*CAPACITIES.values(), "All\ncapacities"]
HUMANS, MIXED = "Humans", "All evaluators"  # rater groups of data_reliability_analysis.GROUPS


@dataclass(frozen=True)
class Row:
    key: str
    moments: tuple[str, ...]
    label: str
    group: str  # rater group
    apart: bool = False  # drawn a little below the rows above it


ROWS = [
    Row("pre", ("pre",), TIME["pre"][0], HUMANS),
    Row("post", ("post",), TIME["post"][0], HUMANS),
    Row("both", STAGES, "Both", HUMANS),
    Row("both_llm", STAGES, "Both, incl.\nLLM scoring", MIXED, apart=True),
]


def soften(color: str, saturation: float = 0.7, lighten: float = 0.04) -> str:
    """The colour with its saturation scaled by `saturation` and its lightness raised by `lighten` (HLS)."""
    h, l, s = colorsys.rgb_to_hls(*to_rgb(color))
    return to_hex(colorsys.hls_to_rgb(h, min(1.0, l + lighten), s * saturation))


SOFT_GREEN = soften(LEVELS[3][1])  # LEVELS' green (#60f070), a little toward pastel


def altman_bands() -> list[tuple[float, str, str]]:
    """Altman's scale as irrCAC defines it (the bounds do not depend on the coefficient passed), lowest first:
    (lower bound, legend label, fill)."""
    scale = Benchmark(coeff=0.0, se=1.0).altman()
    bands = sorted(((lb, ub), name.capitalize()) for (lb, ub), name in zip(scale["scale"], scale["Altman"]))
    # The five level colours of plot_shared_config.LEVELS, lowest first (grey, red, yellow, green, blue).
    fills = [SOFT_GREEN if lv == 3 else color for lv, (_, color) in sorted(LEVELS.items())]
    if len(bands) != len(fills):
        raise RuntimeError(f"irrCAC's Altman scale has {len(bands)} bands, LEVELS has {len(fills)} colours")
    out = []
    for i, (((lb, ub), name), fill) in enumerate(zip(bands, fills)):
        if i == 0:
            out.append((-math.inf, f"{name} (< {ub:g})", fill))
        elif i == len(bands) - 1:
            out.append((lb, f"{name} (≥ {lb:g})", fill))
        else:
            out.append((lb, f"{name} ({lb:g}–{ub:g})", fill))
    return out


BANDS = altman_bands()
UNDEFINED = "#d9d8d2"

TITLE = "Figure 13. Gwet's AC2 and raw agreement between evaluators"
CAPTION = ("Last row includes both LLM-as-judge agents and human evaluators.In bold, Gwet's AC2 with ordinal weights."
            "\nBeneath, raw percent agreement between human evaluators, and standard deviation between their scores (in levels)."
           )
LEGEND_TITLE = "Altman (1991) benchmark scale"

WIDTH_CM, HEIGHT_CM, HEADER_CM, LEGEND_CM = 16, 6.6, 0.0, 1.0
CM = 1 / 2.54
FONT, SMALL, TITLE_FONT = 6.5, 5.5, 8  # points
W, GAP, LABEL_ROWS = 1.0, 0.3, 0.75  # cell width, gap before a set-apart column or row, column label height
LEFT = 0.13  # first guess at the left edge of the grid; moved so the row labels touch the margin
MARGIN_CM = 0.05  # space left and right of the chart


def trunc(v: float) -> float:
    """Truncated toward zero to three decimals, so 0.7999 reads 0.799 and sits in the lower band."""
    return v if np.isnan(v) else math.trunc(v * 1000) / 1000


def fill_for(v: float) -> str:
    if np.isnan(v):
        return UNDEFINED
    return [fill for lower, _, fill in BANDS if v >= lower][-1]


def pa_text(pa: float, sd: float) -> str:
    """'21.4% (0.62)': percent agreement and the mean SD of the scores, in rubric levels."""
    if np.isnan(pa):
        return ""
    return f"{pa * 100:.1f}% ({sd:.2f})"


# --- agreement measures ---------------------------------------------------------------

def pairable(ratings: np.ndarray) -> np.ndarray:
    """Units (rows) rated by at least two evaluators."""
    return ratings[np.sum(~np.isnan(ratings), axis=1) >= 2]


def percent_agreement(ratings: np.ndarray) -> float:
    """Share of pairable units on which every rating is the same level."""
    units = pairable(ratings)
    return float(np.mean([len(set(u[~np.isnan(u)])) == 1 for u in units])) if len(units) else np.nan


def mean_score_sd(ratings: np.ndarray) -> float:
    """Mean over pairable units of the sample SD (ddof = 1) of the levels given to the unit."""
    units = pairable(ratings)
    return float(np.mean(np.nanstd(units, axis=1, ddof=1))) if len(units) else np.nan


# --- data ------------------------------------------------------------------------

def load(path: Path) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """The 'results_vertical' sheet on the rubric's 1-5 scale, and each rater group's evaluators with any rating."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET, dtype={"participante": str})
    df = df[df["capacidad"].isin(CAPACITIES) & df["momento"].isin(STAGES)]
    rated = [c for c in evaluator_columns(df) if df[c].notna().any()]
    df[rated] = df[rated].apply(pd.to_numeric, errors="raise")
    raters = {g: [c for c in rated if re.fullmatch(GROUPS[g], str(c))] for g in (HUMANS, MIXED)}
    for g, cols in raters.items():
        if len(cols) < 2:
            raise SystemExit(f"{path.name}: fewer than two evaluators in group '{g}' have ratings ({cols})")
    if raters[MIXED] == raters[HUMANS]:
        print("WARNING: no LLM agent has ratings; the last row repeats the humans-only 'Both' row")
    return df, raters


def cell(subset: pd.DataFrame, raters: list[str]) -> dict:
    """n (units rated by >= 2 evaluators), AC2, percent agreement, mean SD of the scores and (for comparison
    only) the pairwise agreement; NaN where undefined."""
    active = [c for c in raters if subset[c].notna().any()]
    ratings = subset[active].to_numpy(dtype=float)
    n = int((np.sum(~np.isnan(ratings), axis=1) >= 2).sum()) if active else 0
    out = {"n": n, "raters": active, "ac2": np.nan, "pa": np.nan, "sd": np.nan, "pairwise": np.nan}
    if len(active) < 2 or not n:
        return out
    out["pa"], out["sd"] = percent_agreement(ratings), mean_score_sd(ratings)
    out["pairwise"] = raw_agreement(ratings, count_matrix(ratings))[0]
    try:
        out["ac2"] = gwet_ac2(ratings)
    except (ValueError, ZeroDivisionError):  # no variation at all: the coefficient is undefined
        pass
    return out


def compute(df: pd.DataFrame, raters: dict[str, list[str]]) -> dict:
    """(column, row key) -> cell."""
    res = {}
    for g in COLUMNS:
        rows = df if g == GLOBAL else df[df["capacidad"] == g]
        for row in ROWS:
            res[g, row.key] = cell(rows[rows["momento"].isin(row.moments)], raters[row.group])
    return res


# --- figure ----------------------------------------------------------------------

def write_retrying(path: Path, data: bytes) -> None:
    """OneDrive briefly locks a file it is syncing, so the write is retried."""
    for attempt in range(10):
        try:
            path.write_bytes(data)
            return
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.5)


def row_positions() -> list[float]:
    """Bottom edge of each row, top row first; a set-apart row drops by GAP."""
    ys, y = [], 0.0
    for row in reversed(ROWS):
        ys.append(y)
        y += 1 + (GAP if row.apart else 0)
    return list(reversed(ys))


def figure(res: dict, out: Path) -> None:
    xs = [i * W + (GAP if g == GLOBAL else 0) for i, g in enumerate(COLUMNS)]
    ys = row_positions()
    fig, ax = plt.subplots(figsize=(WIDTH_CM * CM, HEIGHT_CM * CM), facecolor="white")
    for row, y in zip(ROWS, ys):
        for x, g in zip(xs, COLUMNS):
            c = res[g, row.key]
            v = trunc(c["ac2"])
            f = fill_for(v)
            ink = label_ink(f)
            ax.add_patch(plt.Rectangle((x + .03, y + .05), W - .06, .9, color=f, ec="none"))
            ax.text(x + W / 2, y + .62, "–" if np.isnan(v) else f"{v:.3f}", ha="center", va="center",
                    fontsize=FONT, color=ink, fontweight="bold")
            ax.text(x + W / 2, y + .32, pa_text(c["pa"], c["sd"]), ha="center", va="center",
                    fontsize=SMALL, color=ink)
        ax.text(-0.1, y + .5, row.label, ha="right", va="center", fontsize=FONT, color=INK, linespacing=1.1)
    top = ys[0] + 1
    for x, g, label in zip(xs, COLUMNS, COLUMN_LABELS):
        ax.text(x + W / 2, top + 0.1, label, ha="center", va="bottom", fontsize=FONT, color=INK,
                fontweight="bold" if g == GLOBAL else None, linespacing=1.1)
    ax.set_xlim(-0.1, xs[-1] + W)
    ax.set_ylim(0, top + LABEL_ROWS)
    ax.axis("off")
    fig.subplots_adjust(left=LEFT, right=0.98, top=1 - (HEADER_CM + 0.2) / HEIGHT_CM,
                        bottom=(LEGEND_CM + 0.15) / HEIGHT_CM)

    # Shift the grid left until the row labels sit at the margin, and stretch it to the right margin;
    # the legend starts at the same margin.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in ax.texts)
    x = MARGIN_CM / WIDTH_CM
    fig.subplots_adjust(left=LEFT - fig.transFigure.inverted().transform((left, 0))[0] + x, right=1 - x)
    fig.legend(handles=[Patch(facecolor=c, edgecolor="none", label=lab) for _, lab, c in BANDS],
               title=LEGEND_TITLE, loc="upper left", bbox_to_anchor=(x, (LEGEND_CM - 0.1) / HEIGHT_CM),
               ncol=len(BANDS), fontsize=SMALL, title_fontsize=SMALL, alignment="left", handlelength=1.0,
               handleheight=0.8, handletextpad=0.5, columnspacing=0.9, borderaxespad=0, borderpad=0)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor="white")
    plt.close(fig)
    write_retrying(out, buffer.getvalue())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to draw (default: the newest)")
    args = parser.parse_args()
    summary = latest_summary(args.date)
    tag = summary.name.split("_", 1)[0]

    df, raters = load(summary)
    res = compute(df, raters)
    print(f"{summary.name}: humans {', '.join(raters[HUMANS])}; mixed panel {', '.join(raters[MIXED])}")
    print("units rated by >= 2 evaluators (all capacities): "
          + ", ".join(f"{row.key} {res[GLOBAL, row.key]['n']}" for row in ROWS))
    out = OUT_DIR / f"figure13_reliability_analysis_{tag}.png"
    figure(res, out)
    print(f"\n{TITLE}\n{CAPTION}\n(AC2 / percent agreement % (mean SD of scores) / pairwise agreement, not drawn)")
    print(f"{'':9s}" + "".join(f"{g[:14]:>16s}" for g in COLUMNS))
    for row in ROWS:
        print(f"{row.key:9s}" + "".join(f"{trunc(res[g, row.key]['ac2']):>16.3f}" for g in COLUMNS))
        print(f"{'':9s}" + "".join(f"{pa_text(res[g, row.key]['pa'], res[g, row.key]['sd']):>16s}" for g in COLUMNS))
        print(f"{'':9s}" + "".join(f"{'pw ' + format(res[g, row.key]['pairwise'] * 100, '.1f') + '%':>16s}" for g in COLUMNS))
    print(f"\nsoftened green: {LEVELS[3][1]} -> {SOFT_GREEN}")
    print("->", out.relative_to(OUT_DIR.parent.parent).as_posix())
