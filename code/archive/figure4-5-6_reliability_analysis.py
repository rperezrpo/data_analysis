"""Figures 4 and 6: inter-rater reliability by capacity and moment. One PNG per indicator.

    Figure 4   raw agreement: share of rater pairs that gave the same level
    Figure 6   Gwet's AC2, ordinal weights, chance term over the full 1-5 scale

Each figure is a grid with one column per capacity plus 'All capacities' (the seven pooled, set apart) and
four rows (ROWS):
    Pre-workshop                  human evaluators (H1 ...), pre-workshop interviews
    Post-workshop                 human evaluators, post-workshop interviews
    Both                          human evaluators, all interviews
    Both, incl. LLM scoring       human evaluators and LLM agents (A1 ...) pooled as raters, all interviews
The last row is set apart: it measures agreement in the mixed panel, so it shows whether adding the agents
raises or lowers the agreement of the humans alone (the row above it). The rater groups are those of
data_reliability_analysis.py (GROUPS). Evaluators without a single rating in a cell's scope are left out,
and one who rated only part of the interviews adds only those. A unit is one interview x one capacity;
only units rated by at least two evaluators count.

The two indicators are computed by raw_agreement() and gwet_ac2() of
data_reliability_analysis.py, so the 'All capacities' cells of the two 'Both' rows equal the reliability
table's values for 'Humans' and 'All evaluators'.

Colours:
- Figures 4 and 6 by Altman's (1991) scale with bounds and names from irrCAC (Benchmark.altman()), its
  five bands in the five LEVELS colours of plot_shared_config.py (poor grey ... very good blue); a value on
  a bound belongs to the higher band, as in irrCAC. The band is read from the point estimate, not from
  irrCAC's probabilistic benchmarking (which needs the standard error), so a colour always matches its value.
  Figure 4 gives the bounds as percentages, like its cells. Altman's scale was set for chance-corrected
  coefficients (kappa type), not for raw agreement, which includes the agreement expected by chance; the
  legend says so.
Values are truncated toward zero to three decimals so they never contradict the colour. A coefficient that
is undefined (no unit with two ratings, or no variation at all) is drawn as a grey cell with a dash.

Input: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one unless --date
is given. Outputs (PNG only, 16 cm wide, 300 dpi), in results/figures/:
    figure4_raw_agreement_YYYYMMDD.png, figure6_gwet_ac2_YYYYMMDD.png
The values are also printed to the console.

Usage (from data_analysis/):
    python code/figure4-5-6_reliability_analysis.py
    python code/figure4-5-6_reliability_analysis.py --date 20261106
"""
import argparse
import io
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from irrCAC.benchmark import Benchmark
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

# Benchmark bands, lowest first: (lower bound, legend label, fill). Altman's five take the five LEVELS
# colours in order.


def altman_bands(percent: bool = False) -> list[tuple[float, str, str]]:
    """Altman's scale as irrCAC defines it (the bounds do not depend on the coefficient passed).

    With percent, the legend labels give the bounds as percentages (20%) instead of proportions (0.2).
    """
    def fmt(b: float) -> str:
        return f"{b * 100:.0f}%" if percent else f"{b:g}"

    scale = Benchmark(coeff=0.0, se=1.0).altman()
    bands = sorted(((lb, ub), name.capitalize()) for (lb, ub), name in zip(scale["scale"], scale["Altman"]))
    # The five level colours of plot_shared_config.LEVELS, lowest first (grey, red, yellow, green, blue).
    fills = [color for _, (_, color) in sorted(LEVELS.items())]
    if len(bands) != len(fills):
        raise RuntimeError(f"irrCAC's Altman scale has {len(bands)} bands, LEVELS has {len(fills)} colours")
    out = []
    for i, (((lb, ub), name), fill) in enumerate(zip(bands, fills)):
        if i == 0:
            out.append((-math.inf, f"{name} (< {fmt(ub)})", fill))
        elif i == len(bands) - 1:
            out.append((lb, f"{name} (≥ {fmt(lb)})", fill))
        elif percent:
            out.append((lb, f"{name} ({lb * 100:.0f}–{fmt(ub)})", fill))
        else:
            out.append((lb, f"{name} ({fmt(lb)}–{fmt(ub)})", fill))
    return out


UNDEFINED = "#d9d8d2"


def raw_share(ratings: np.ndarray) -> float:
    return raw_agreement(ratings, count_matrix(ratings))[0]


@dataclass(frozen=True)
class Indicator:
    key: str
    number: int
    slug: str  # output file name: figure<number>_<slug>_YYYYMMDD.png
    title: str
    caption: str
    compute: Callable[[np.ndarray], float]
    bands: list  # benchmark bands, lowest first: (lower bound, legend label, fill)
    legend_title: str
    percent: bool = False  # print the value as a percentage


CAPTION_END = "; last row pools the human evaluators and the LLM agents"
INDICATORS = [
    Indicator("raw", 4, "raw_agreement", "Figure 13. Raw exact agreement between evaluators",
              "Share of evaluator pairs that gave the same level, averaged over interviews" + CAPTION_END,
              raw_share, altman_bands(percent=True),
              "Altman (1991) benchmark scale (set for chance-corrected coefficients; applied here to raw agreement)",
              percent=True),
    Indicator("ac2", 6, "gwet_ac2", "Figure 15. Gwet's AC2 between evaluators",
              "Gwet's AC2 with ordinal weights, by capacity and moment" + CAPTION_END,
              gwet_ac2, altman_bands(), "Altman (1991) benchmark scale"),
]

WIDTH_CM, HEIGHT_CM, HEADER_CM, LEGEND_CM = 16, 7.6, 1.05, 1.0
CM = 1 / 2.54
FONT, SMALL, TITLE_FONT = 6.5, 5.5, 8  # points
W, GAP, LABEL_ROWS = 1.0, 0.3, 0.75  # cell width, gap before a set-apart column or row, column label height


def trunc(v: float) -> float:
    """Truncated toward zero to three decimals, so 0.7999 reads 0.799 and sits in the lower band."""
    return v if np.isnan(v) else math.trunc(v * 1000) / 1000


def fill_for(v: float, ind: Indicator) -> str:
    if np.isnan(v):
        return UNDEFINED
    return [fill for lower, _, fill in ind.bands if v >= lower][-1]


def text_for(v: float, ind: Indicator) -> str:
    if np.isnan(v):
        return "–"
    return f"{v * 100:.1f}%" if ind.percent else f"{v:.3f}"


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
    """n (units rated by >= 2 evaluators) and every indicator; NaN where it is undefined."""
    active = [c for c in raters if subset[c].notna().any()]
    ratings = subset[active].to_numpy(dtype=float)
    n = int((np.sum(~np.isnan(ratings), axis=1) >= 2).sum()) if active else 0
    out = {"n": n, "raters": active}
    for ind in INDICATORS:
        try:
            out[ind.key] = ind.compute(ratings) if len(active) >= 2 and n else np.nan
        except (ValueError, ZeroDivisionError):  # no variation at all: the coefficient is undefined
            out[ind.key] = np.nan
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


def figure(res: dict, ind: Indicator, out: Path) -> None:
    xs = [i * W + (GAP if g == GLOBAL else 0) for i, g in enumerate(COLUMNS)]
    ys = row_positions()
    fig, ax = plt.subplots(figsize=(WIDTH_CM * CM, HEIGHT_CM * CM), facecolor="white")
    for row, y in zip(ROWS, ys):
        for x, g in zip(xs, COLUMNS):
            v = trunc(res[g, row.key][ind.key])
            f = fill_for(v, ind)
            ax.add_patch(plt.Rectangle((x + .03, y + .05), W - .06, .9, color=f, ec="none"))
            ax.text(x + W / 2, y + .5, text_for(v, ind), ha="center", va="center", fontsize=FONT,
                    color=label_ink(f), fontweight="bold" if g == GLOBAL else None)
        ax.text(-0.1, y + .5, row.label, ha="right", va="center", fontsize=FONT, color=INK, linespacing=1.1)
    top = ys[0] + 1
    for x, g, label in zip(xs, COLUMNS, COLUMN_LABELS):
        ax.text(x + W / 2, top + 0.1, label, ha="center", va="bottom", fontsize=FONT, color=INK,
                fontweight="bold" if g == GLOBAL else None, linespacing=1.1)
    ax.set_xlim(-0.1, xs[-1] + W)
    ax.set_ylim(0, top + LABEL_ROWS)
    ax.axis("off")
    fig.subplots_adjust(left=0.13, right=0.98, top=1 - (HEADER_CM + 0.2) / HEIGHT_CM,
                        bottom=(LEGEND_CM + 0.15) / HEIGHT_CM)

    # Title, caption and legend at the left edge of the whole chart: the row labels.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in ax.texts)
    x = fig.transFigure.inverted().transform((left, 0))[0]
    fig.text(x, 1 - 0.15 / HEIGHT_CM, ind.title, ha="left", va="top", fontsize=TITLE_FONT,
             fontweight="bold", color=INK)
    fig.text(x, 1 - 0.55 / HEIGHT_CM, ind.caption, ha="left", va="top", fontsize=FONT, color=MUTED)
    fig.legend(handles=[Patch(facecolor=c, edgecolor="none", label=lab) for _, lab, c in ind.bands],
               title=ind.legend_title, loc="upper left", bbox_to_anchor=(x, (LEGEND_CM - 0.1) / HEIGHT_CM),
               ncol=len(ind.bands), fontsize=SMALL, title_fontsize=SMALL, alignment="left", handlelength=1.0,
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
    root = OUT_DIR.parent.parent
    for ind in INDICATORS:
        out = OUT_DIR / f"figure{ind.number}_{ind.slug}_{tag}.png"
        figure(res, ind, out)
        print(f"\n{ind.title}")
        print(f"{'':9s}" + "".join(f"{g[:10]:>11s}" for g in COLUMNS))
        for row in ROWS:
            print(f"{row.key:9s}" + "".join(f"{trunc(res[g, row.key][ind.key]):11.3f}" for g in COLUMNS))
        print("->", out.relative_to(root).as_posix())
