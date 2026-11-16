"""Figure 1.3: baseline and posterior condition. Side-by-side boxplots of the pre- and post-workshop levels
by capacity, as rated by the human evaluators.

Combines Figure 1 (pre-workshop) and Figure 4 (post-workshop): for each capacity, a pre-workshop box
on the left and a post-workshop box on the right, each pooling the ratings of the human evaluators
(H1 ...) for that moment. Evaluators are the columns of the ratings summary; one without a single
rating yet (an empty rater folder) is left out, and one who rated only part of the interviews adds
only those. Pre and post are pooled independently, so a box is not restricted to paired participants.
Levels on the rubric's 1-5 scale with the names of rubric v5 on (Absence ... Leadership).
Boxes in the pre- and post-workshop colours of TIME (plot_shared_config.py), with a legend at the foot.
Boxes: quartiles; black line: median, a little wider than the box so it shows on an edge;
whiskers: 1.5 IQR; dots: values beyond the whiskers. With only five possible levels a quartile
often equals the median, so many boxes have the median on an edge; when the middle half of the
values sits on one level (Q1 = Q3) the box is drawn as a thick bar.
The image is 16 cm wide (WIDTH_CM): a band of HEADER_CM for the title and caption over a plot area of
PLOT_CM, with small fonts; the caption is also printed to the console. White background.

Input: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one
unless --date is given. Output: results/figures/figure1.3_baseline_condition_YYYYMMDD.png (16 x 5.9 cm, 300 dpi).

Usage (from data_analysis/):
    python code/figure1.3_baseline_condition.py
    python code/figure1.3_baseline_condition.py --date 20261106
"""
import argparse
import io
import re
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from plot_shared_config import (
    CAPACITIES, INK, MUTED, OUT_DIR, RUBRIC_V5_NAMES, STAGES, TIME, VERTICAL_SHEET, evaluator_columns,
    latest_summary,
)

HUMAN = re.compile(r"H\d+")
TITLE = "Figure 10. Distribution of appropriation levels of participants before and after the workshops"
CAPTION = "Median and quartiles of the pre- and post-workshop levels by capacity, as rated by the human evaluators"
LEGEND_TITLE = "Moment of assessment"
OFFSET = 0.19  # distance of the pre and post box centres from the capacity's centre, in capacity steps
WIDTH = 0.28  # box width, in capacity steps; leaves a gap between the pair's protruding medians
# Layout in cm, top to bottom: header (title and caption), plot area, capacity labels and legend.
WIDTH_CM, HEADER_CM, PLOT_CM, BOTTOM_CM = 16, 1.05, 3.5, 1.35
LEFT = 0.13  # left edge of the plot area, as a fraction of the width; the right margin mirrors the left one
CM = 1 / 2.54
FONT, SMALL, TITLE_FONT = 6.5, 5.5, 8  # points


def load(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Pre- and post-workshop human ratings in long form (capacidad, momento, transcripcion, evaluator,
    level), and the human evaluators that rated at least one interview."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET)
    df = df[df["momento"].isin(STAGES) & df["capacidad"].isin(CAPACITIES)]
    humans = [c for c in evaluator_columns(df) if HUMAN.fullmatch(c) and df[c].notna().any()]
    if not humans:
        raise SystemExit(f"{path.name}: no human evaluator has rated an interview")
    long = df.melt(id_vars=["capacidad", "momento", "transcripcion"], value_vars=humans, var_name="evaluator",
                   value_name="level").dropna(subset=["level"])
    off_scale = sorted(set(long["level"]) - set(range(1, 6)))
    if off_scale:
        raise ValueError(f"{path.name}: levels {off_scale} are outside the rubric's 1-5 scale")
    return long, humans


def draw_boxes(ax: plt.Axes, data: list, positions: list[float], color: str) -> None:
    """One box per capacity for a single moment, in that moment's colour."""
    bp = ax.boxplot(
        data, positions=positions, widths=WIDTH, patch_artist=True, whis=1.5, zorder=3, manage_ticks=False,
        boxprops=dict(facecolor=color, edgecolor=color, linewidth=0.8),
        medianprops=dict(color=INK, linewidth=1.4, solid_capstyle="butt", zorder=5),
        whiskerprops=dict(color=MUTED, linewidth=0.7), capprops=dict(color=MUTED, linewidth=0.7),
        flierprops=dict(marker="o", markersize=2.5, markerfacecolor=color,
                        markeredgecolor="white", markeredgewidth=0.4),
    )
    # The median sticks out of the box on both sides, so it stays visible on an edge.
    # A flat box (Q1 = Q3 = median) would hide its median: draw it as a thick bar in the box colour.
    for values, med in zip(data, bp["medians"]):
        x0, x1 = med.get_xdata()[:2]
        med.set_xdata([x0 - 0.03, x1 + 0.03])
        q1, q3 = pd.Series(values).quantile([0.25, 0.75])
        if q1 == q3:
            med.set(color=color, linewidth=3)


def plot(df: pd.DataFrame, humans: list[str], summary: Path) -> None:
    caps = list(CAPACITIES)
    height_cm = HEADER_CM + PLOT_CM + BOTTOM_CM

    fig, ax = plt.subplots(figsize=(WIDTH_CM * CM, height_cm * CM), facecolor="white")
    ax.set_facecolor("white")
    for stage, shift in zip(STAGES, (-OFFSET, OFFSET)):
        data = [df.query("capacidad == @cap and momento == @stage")["level"].values for cap in caps]
        draw_boxes(ax, data, [i + shift for i in range(len(caps))], TIME[stage][1])
    ax.set_xticks(range(len(caps)), list(CAPACITIES.values()))
    ax.set_xlim(-0.6, len(caps) - 0.4)
    ax.set_ylim(0.5, 5.5)
    ax.set_yticks(range(1, 6), [RUBRIC_V5_NAMES[lv - 1] for lv in range(1, 6)])
    ax.yaxis.grid(True, zorder=0, linewidth=0.5)
    ax.tick_params(axis="x", labelsize=FONT, labelcolor=INK, pad=2)
    ax.tick_params(axis="y", labelsize=FONT, pad=2)

    fig.subplots_adjust(left=LEFT, top=1 - HEADER_CM / height_cm, bottom=BOTTOM_CM / height_cm)
    # Title, caption and legend at the left edge of the whole chart: the level names.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in ax.get_yticklabels())
    x = fig.transFigure.inverted().transform((left, 0))[0]
    # Right margin as wide as the left one, so the chart sits centred on the page.
    fig.subplots_adjust(right=1 - x)
    fig.text(x, 1 - 0.15 / height_cm, TITLE, ha="left", va="top", fontsize=TITLE_FONT, fontweight="bold", color=INK)
    fig.text(x, 1 - 0.55 / height_cm, CAPTION, ha="left", va="top", fontsize=FONT, color=MUTED)
    fig.legend(
        [plt.Rectangle((0, 0), 1, 1, color=TIME[s][1]) for s in STAGES], [TIME[s][0] for s in STAGES],
        title=LEGEND_TITLE, title_fontsize=SMALL, alignment="left",
        ncol=len(STAGES), bbox_to_anchor=(x, 0.06 / height_cm), loc="lower left", fontsize=SMALL,
        handlelength=1.0, handleheight=0.8, handletextpad=0.5, columnspacing=0.9, borderaxespad=0, borderpad=0,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"figure1.3_baseline_condition_{summary.name.split('_', 1)[0]}.png"
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

    print(f"human evaluators {', '.join(humans)}: Q1/median/Q3 (n), pre | post")
    for cap in caps:
        cells = []
        for stage in STAGES:
            s = df.query("capacidad == @cap and momento == @stage")["level"].describe()
            cells.append(f"{s['25%']:.2f}/{s['50%']:.1f}/{s['75%']:.2f} ({int(s['count'])})")
        print(f"{cap:24s} {' | '.join(cells)}")
    print(f"\n{TITLE}\n{CAPTION}")
    print("->", out.relative_to(OUT_DIR.parent.parent).as_posix(), f"({WIDTH_CM} x {height_cm:g} cm)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to draw (default: the newest)")
    args = parser.parse_args()
    summary = latest_summary(args.date)
    plot(*load(summary), summary)
