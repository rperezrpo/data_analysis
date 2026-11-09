"""Figure 2: level distribution. Pre- and post-workshop appropriation levels by capacity, pooled over all human ratings.

Two diverging stacked bars per capacity: pre-workshop on the left, post-workshop on the right.

Heights and labels are the share of the bar's ratings at each level (each bar sums to 100%);
segments under MIN_LABEL % are left unlabelled (too thin for the text).

Levels on the rubric's 1-5 scale with the names of rubric v5 on (Absence ... Leadership), coloured as
LEVELS in plot_shared_config.py.

The lowest levels (LEVELS_BELOW: Awareness, Absence) stack downwards from the zero line, the others upwards.

Input: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one
unless --date is given. Output: results/figures/figure2_level_distribution_YYYYMMDD.png (16 cm wide, 300 dpi).

Usage (from data_analysis/):
    python code/figure2_level_distribution.py
    python code/figure2_level_distribution.py --date 20261106
"""
import argparse
import io
import re
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from plot_shared_config import (
    CAPACITIES, INK, LEVELS, LEVELS_BELOW, MUTED, OUT_DIR, RUBRIC_OFFSET, RUBRIC_V5_NAMES, STAGES,
    VERTICAL_SHEET, evaluator_columns, label_ink, latest_summary,
)

HUMAN = re.compile(r"H\d+")
TITLE = "Figure 2. Appropriation levels of participants before and after the workshops"
CAPTION = ("Share of ratings at each level by capacity, pooled over all human evaluators; "
           "left bar pre-workshop, right bar post-workshop")
LEGEND_TITLE = "Appropriation level of the capacity"
# Level on the 0-4 scale of LEVELS -> (rubric v5 name, colour).
STYLES = {lv: (RUBRIC_V5_NAMES[lv], color) for lv, (_, color) in LEVELS.items()}
# Stacking order outwards from the zero line.
BELOW = list(LEVELS_BELOW)
ABOVE = [lv for lv in sorted(LEVELS) if lv not in LEVELS_BELOW]
OFFSET = 0.19  # distance of the pre and post bar centres from the capacity's centre, in capacity steps
WIDTH = 0.34  # bar width, in capacity steps
MIN_LABEL = 8  # % of a bar below which a segment gets no label
TICK_STEP = 20  # % between gridlines
# Layout in cm, top to bottom: header (title and caption), plot area, capacity labels and legend.
WIDTH_CM, HEADER_CM, PLOT_CM, BOTTOM_CM = 16, 1.05, 4.5, 1.35
LEFT = 0.13  # left edge of the plot area, as a fraction of the width; the right margin mirrors the left one
CM = 1 / 2.54
FONT, SMALL, TITLE_FONT = 6.5, 5.5, 8  # points


def load(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Every human rating in long form (capacidad, momento, evaluator, level on the 0-4 scale), and the
    human evaluators that rated at least one interview."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET)
    df = df[df["capacidad"].isin(CAPACITIES) & df["momento"].isin(STAGES)]
    humans = [c for c in evaluator_columns(df) if HUMAN.fullmatch(c) and df[c].notna().any()]
    if not humans:
        raise SystemExit(f"{path.name}: no human evaluator has rated an interview")
    long = df.melt(id_vars=["capacidad", "momento"], value_vars=humans, var_name="evaluator",
                   value_name="level").dropna(subset=["level"])
    off_scale = sorted(set(long["level"]) - set(range(1, 6)))
    if off_scale:
        raise ValueError(f"{path.name}: levels {off_scale} are outside the rubric's 1-5 scale")
    long["level"] = long["level"].astype(int) - RUBRIC_OFFSET
    return long, humans


def draw_bar(ax: plt.Axes, x: float, shares: pd.Series) -> None:
    """One stack around the zero line, each segment labelled with its share of the bar."""
    for direction, levels in ((-1, BELOW), (1, ABOVE)):
        edge = 0.0
        for level in levels:
            share = float(shares.get(level, 0))
            if share == 0:
                continue
            color = STYLES[level][1]
            ax.bar(x, direction * share, WIDTH, bottom=edge, color=color, edgecolor="white", linewidth=0.6, zorder=3)
            if share >= MIN_LABEL:
                # Round half up, so 2 of 16 reads 13% rather than 12%.
                ax.text(x, edge + direction * share / 2, f"{int(share + 0.5)}%", ha="center", va="center",
                        fontsize=SMALL, color=label_ink(color), zorder=4)
            edge += direction * share


def plot(ratings: pd.DataFrame, humans: list[str], summary: Path) -> None:
    caps = list(CAPACITIES)
    counts = (ratings.groupby(["capacidad", "momento", "level"]).size().unstack("level", fill_value=0)
              .reindex(columns=sorted(LEVELS), fill_value=0))
    shares = counts.div(counts.sum(axis=1), axis=0) * 100
    height_cm = HEADER_CM + PLOT_CM + BOTTOM_CM

    fig, ax = plt.subplots(figsize=(WIDTH_CM * CM, height_cm * CM), facecolor="white")
    ax.set_facecolor("white")
    for i, cap in enumerate(caps):
        for stage, sign in zip(STAGES, (-1, 1)):
            if (cap, stage) in shares.index:
                draw_bar(ax, i + sign * OFFSET, shares.loc[(cap, stage)])

    # Symmetric share axis around the zero line, wide enough for the taller side of any bar.
    ymax = TICK_STEP * -(-max(shares[ABOVE].sum(axis=1).max(), shares[BELOW].sum(axis=1).max()) // TICK_STEP)
    ax.set_ylim(-ymax, ymax)
    ticks = range(-int(ymax), int(ymax) + 1, TICK_STEP)
    ax.set_yticks(ticks, [f"{abs(t)}%" for t in ticks])
    ax.set_xticks(range(len(caps)), list(CAPACITIES.values()))
    ax.set_xlim(-0.6, len(caps) - 0.4)
    ax.yaxis.grid(True, zorder=0, linewidth=0.5)
    ax.axhline(0, color=MUTED, linewidth=0.7, zorder=5)
    ax.tick_params(axis="x", labelsize=FONT, labelcolor=INK, pad=2)
    ax.tick_params(axis="y", labelsize=FONT, pad=2)

    fig.subplots_adjust(left=LEFT, top=1 - HEADER_CM / height_cm, bottom=BOTTOM_CM / height_cm)
    # Title, caption and legend at the left edge of the whole chart: the share labels.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in ax.get_yticklabels())
    x = fig.transFigure.inverted().transform((left, 0))[0]
    # Right margin as wide as the left one, so the chart sits centred on the page.
    fig.subplots_adjust(right=1 - x)
    fig.text(x, 1 - 0.15 / height_cm, TITLE, ha="left", va="top", fontsize=TITLE_FONT, fontweight="bold", color=INK)
    fig.text(x, 1 - 0.55 / height_cm, CAPTION, ha="left", va="top", fontsize=FONT, color=MUTED)

    fig.legend(
        [plt.Rectangle((0, 0), 1, 1, color=STYLES[lv][1]) for lv in sorted(LEVELS)],
        [STYLES[lv][0] for lv in sorted(LEVELS)],
        title=LEGEND_TITLE, ncol=len(LEVELS), bbox_to_anchor=(x, 0.06 / height_cm),
        loc="lower left", fontsize=SMALL, title_fontsize=SMALL, alignment="left", handlelength=1.0,
        handleheight=0.8, handletextpad=0.5, columnspacing=0.9, borderaxespad=0, borderpad=0,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"figure2_level_distribution_{summary.name.split('_', 1)[0]}.png"
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

    print(f"human evaluators {', '.join(humans)}: ratings per capacity, moment and level")
    table = counts.rename(columns={lv: STYLES[lv][0] for lv in LEVELS})
    print(table.assign(total=table.sum(axis=1)).to_string())
    print("\nratings per evaluator:", ratings.groupby("evaluator").size().to_dict())
    print(f"\n{TITLE}\n{CAPTION}")
    print("->", out.relative_to(OUT_DIR.parent.parent).as_posix(), f"({WIDTH_CM} x {height_cm:g} cm)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to draw (default: the newest)")
    args = parser.parse_args()
    summary = latest_summary(args.date)
    plot(*load(summary), summary)
