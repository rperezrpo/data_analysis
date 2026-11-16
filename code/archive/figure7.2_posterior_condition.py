"""Figure 4.2: posterior condition by evaluator. Horizontal boxplots of the post-workshop levels, one per
capacity and human evaluator.

Capacities on the y axis, top to bottom; within each capacity one box per human evaluator (H1 ...),
all in the post-workshop colour of TIME, each labelled (H1 ...) just left of the Absence line. Evaluators
without a single post-workshop rating yet are left out; one who rated only part of the interviews
gets a box from those only. Levels on the x axis, rubric's 1-5 scale with the names of rubric v5
(Absence ... Leadership).
Boxes: quartiles; black line: median, a little taller than the box so it shows on an edge;
whiskers: 1.5 IQR; dots: values beyond the whiskers. When the middle half of the values sits on
one level (Q1 = Q3) the box is drawn as a thick bar.
The image is 16 cm wide (WIDTH_CM): a band of HEADER_CM for title and caption over a plot
area of PLOT_CM; the caption is also printed to the console. White background.

Input: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one
unless --date is given. Output: results/figures/figure4.2_posterior_condition_YYYYMMDD.png (16 x 12.1 cm, 300 dpi).

Usage (from data_analysis/):
    python code/figure4.2_posterior_condition.py
    python code/figure4.2_posterior_condition.py --date 20261106
"""
import argparse
import io
import re
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from plot_shared_config import (
    CAPACITIES, GRID, INK, MUTED, OUT_DIR, RUBRIC_V5_NAMES, TIME, VERTICAL_SHEET, evaluator_columns, latest_summary,
    run_date,
)

COLOR = TIME["post"][1]
HUMAN = re.compile(r"H\d+")
TITLE = "Figure 4. Distribution of appropriation level of participants after the workshop"
CAPTION = "Median and quartiles of the post-workshop levels by capacity and human evaluator"
GROUP = 0.7  # height taken by the boxes of one capacity, in capacity steps; the rest separates capacities
# Layout in cm, top to bottom: header (title and caption), plot area, level labels.
WIDTH_CM, HEADER_CM, PLOT_CM, BOTTOM_CM = 16, 1.05, 10.5, 0.55
X_MIN = 0.72  # left end of the level axis: just room for the evaluator labels left of Absence (1)
EV_X = 0.96  # right edge of the evaluator labels, in level units
LEFT = 0.17  # first guess of the plot area's left edge, as a fraction of the width
RIGHT_MARGIN_LEFT = 0.02  # page margin on both sides, as a fraction of the width
CM = 1 / 2.54
FONT, TITLE_FONT = 6.5, 8  # points


def load(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Post-workshop human ratings in long form (capacidad, transcripcion, evaluator, level), and the
    human evaluators that rated at least one post-workshop interview."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET)
    df = df[(df["momento"] == "post") & df["capacidad"].isin(CAPACITIES)]
    humans = [c for c in evaluator_columns(df) if HUMAN.fullmatch(c) and df[c].notna().any()]
    if not humans:
        raise SystemExit(f"{path.name}: no human evaluator has rated a post-workshop interview")
    long = df.melt(id_vars=["capacidad", "transcripcion"], value_vars=humans, var_name="evaluator",
                   value_name="level").dropna(subset=["level"])
    off_scale = sorted(set(long["level"]) - set(range(1, 6)))
    if off_scale:
        raise ValueError(f"{path.name}: levels {off_scale} are outside the rubric's 1-5 scale")
    return long, humans


def plot(df: pd.DataFrame, humans: list[str], summary: Path) -> None:
    caps = list(CAPACITIES)
    n_ev = len(humans)
    height_cm = HEADER_CM + PLOT_CM + BOTTOM_CM
    box_h = GROUP / n_ev * 0.8  # box height, in capacity steps; the rest is the gap between boxes

    fig, ax = plt.subplots(figsize=(WIDTH_CM * CM, height_cm * CM), facecolor="white")
    ax.set_facecolor("white")
    ax.set_ylim(len(caps) - 0.5, -0.5)  # first capacity on top
    ax.set_xlim(X_MIN, 5.5)
    fig.subplots_adjust(left=LEFT, top=1 - HEADER_CM / height_cm, bottom=BOTTOM_CM / height_cm)

    for k, ev in enumerate(humans):
        # Evaluators top to bottom within each capacity, in the order H1, H2 ...
        offset = (k - (n_ev - 1) / 2) * GROUP / n_ev
        data, pos = [], []
        for i, cap in enumerate(caps):
            values = df.query("capacidad == @cap and evaluator == @ev")["level"].values
            if len(values):
                data.append(values)
                pos.append(i + offset)
                ax.text(EV_X, i + offset, ev, ha="right", va="center",
                        fontsize=FONT - 1, color=MUTED)
        bp = ax.boxplot(
            data, positions=pos, widths=box_h, vert=False, patch_artist=True, whis=1.5, zorder=3,
            boxprops=dict(facecolor=COLOR, edgecolor=COLOR, linewidth=0.6),
            medianprops=dict(color=INK, linewidth=1.2, solid_capstyle="butt", zorder=5),
            whiskerprops=dict(color=MUTED, linewidth=0.6), capprops=dict(color=MUTED, linewidth=0.6),
            capwidths=box_h * 0.5,
            flierprops=dict(marker="o", markersize=2.2, markerfacecolor=COLOR,
                            markeredgecolor="white", markeredgewidth=0.3),
        )
        # The median sticks out of the box on both sides, so it stays visible on an edge.
        # A flat box (Q1 = Q3 = median) would hide its median: draw it as a thick bar in the box colour.
        for values, med in zip(data, bp["medians"]):
            y0, y1 = med.get_ydata()[:2]
            med.set_ydata([y0 - 0.02, y1 + 0.02])
            q1, q3 = pd.Series(values).quantile([0.25, 0.75])
            if q1 == q3:
                med.set(color=COLOR, linewidth=3)
                med.set_ydata([y0, y1])

    ax.set_yticks(range(len(caps)), list(CAPACITIES.values()))
    ax.set_xticks(range(1, 6), [RUBRIC_V5_NAMES[lv - 1] for lv in range(1, 6)])
    ax.xaxis.grid(True, zorder=0, linewidth=0.5)
    # Thin separators between capacity groups.
    for i in range(1, len(caps)):
        ax.hlines(i - 0.5, 1, 5.5, color=GRID, linewidth=0.5, zorder=0)
    ax.tick_params(axis="y", labelsize=FONT, labelcolor=INK, pad=3)
    ax.tick_params(axis="x", labelsize=FONT, pad=2)

    # Title and caption at the left edge of the whole chart: the capacity names.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in ax.get_yticklabels())
    x = fig.transFigure.inverted().transform((left, 0))[0]
    # Shift the plot so the labels start at the page margin, and mirror that margin on the right.
    fig.subplots_adjust(left=LEFT - x + RIGHT_MARGIN_LEFT, right=1 - RIGHT_MARGIN_LEFT)
    x = RIGHT_MARGIN_LEFT
    fig.text(x, 1 - 0.15 / height_cm, TITLE, ha="left", va="top", fontsize=TITLE_FONT, fontweight="bold", color=INK)
    fig.text(x, 1 - 0.55 / height_cm, CAPTION, ha="left", va="top", fontsize=FONT, color=MUTED)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"figure4.2_posterior_condition_{summary.name.split('_', 1)[0]}.png"
    # Render to memory first: OneDrive briefly locks a file it is syncing, so the write is retried.
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor="white")
    plt.close(fig)
    for attempt in range(10):
        try:
            out.write_bytes(buffer.getvalue())
            break
        except OSError:
            if attempt == 9:
                raise
            time.sleep(0.5)

    print("post-workshop, by human evaluator: Q1/median/Q3 (n)")
    for cap in caps:
        for ev in humans:
            s = df.query("capacidad == @cap and evaluator == @ev")["level"].describe()
            if s["count"]:
                print(f"{cap:24s} {ev:3s} {s['25%']:.2f}/{s['50%']:.1f}/{s['75%']:.2f} ({int(s['count'])})")
    print(f"\n{TITLE}\n{CAPTION}")
    print("->", out.relative_to(OUT_DIR.parent.parent).as_posix(), f"({WIDTH_CM} x {height_cm:g} cm)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to draw (default: the newest)")
    args = parser.parse_args()
    summary = latest_summary(args.date)
    plot(*load(summary), summary)
