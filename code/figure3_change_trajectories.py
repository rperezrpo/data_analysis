"""Figure 3: change trajectories. Pre- to post-workshop paths by capacity, as rated by the human evaluators.

One panel per capacity. Each line joins a pre-workshop level to a post-workshop level: a path is one
human evaluator's pair of ratings of one participant (the same evaluator rated both interviews), so
the human evaluators (H1 ...) are pooled as in Figure 1. An evaluator without a single rating yet
(an empty rater folder) is left out; one who rated only part of the interviews adds only the
participants they rated at both moments. Line thickness: number of paths; line colour: direction of
the change only (DIRECTIONS: reduces, stays, improves; not graded by the number of levels). Grey dots
and numbers: ratings at each level before and after; pre-workshop on the left of each panel, post on
the right (no Pre/Post labels). Capacities below the panels, and under them two legends: 'Type of
trajectory' (colour) and 'Quantity of trajectories' (thickness, counted over all evaluators' paths).
Levels on the rubric's 1-5 scale with the names of rubric v5 on (Absence ... Leadership).
The image is 16 x 5 cm (WIDTH_CM x HEIGHT_CM): a header band for title and caption over the
panels, with small fonts; the caption and the path counts are also printed to the console. White background.

Input: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one
unless --date is given. Output: results/figures/figure3_change_trajectories_YYYYMMDD.png (16 x 5 cm, 300 dpi).

Usage (from data_analysis/):
    python code/figure3_change_trajectories.py
    python code/figure3_change_trajectories.py --date 20261106
"""
import argparse
import io
import re
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

from plot_shared_config import (
    CAPACITIES, CHANGES, INK, MUTED, OUT_DIR, RUBRIC_V5_NAMES, STAGES, VERTICAL_SHEET, evaluator_columns,
    latest_summary,
)

HUMAN = re.compile(r"H\d+")
TITLE = "Figure 3. Learning trajectories of participants through the workshops"
CAPTION = ("Paths from pre- to post-workshop level by capacity, as rated by the human evaluators; "
           "numbers count ratings at each level")
LINE_W = 0.35  # points of line width per path
DOT_AREA = 2.5  # points^2 of dot area per rating
WIDTH_KEY = [1, 5, 10]  # path counts shown in the thickness legend
# Sign of the change -> (label, colour); colours taken from the change scale of plot_shared_config.py.
DIRECTIONS = {-1: ("Reduces", CHANGES[-1][1]), 0: ("Stays", CHANGES[0][1]), 1: ("Improves", CHANGES[2][1])}
# Layout in cm, top to bottom: header (title, caption), panels, capacity labels, gap, legends.
WIDTH_CM, HEIGHT_CM, HEADER_CM, BOTTOM_CM = 16, 5, 1.0, 1.4
LEGEND_GAP_CM = 0.5  # horizontal space between the two legends
LEFT = 0.13  # left edge of the panels, as a fraction of the width; the right margin mirrors the left one
CM = 1 / 2.54
FONT, SMALL, TITLE_FONT = 6.5, 5.5, 8  # points


def load(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Human pre/post pairs in long form (capacidad, participante, evaluator, pre, post, change), and
    the human evaluators that rated at least one interview."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET, dtype={"participante": str})
    df = df[df["capacidad"].isin(CAPACITIES)]
    humans = [c for c in evaluator_columns(df) if HUMAN.fullmatch(c) and df[c].notna().any()]
    if not humans:
        raise SystemExit(f"{path.name}: no human evaluator has rated an interview")
    long = df.melt(id_vars=["capacidad", "participante", "momento"], value_vars=humans, var_name="evaluator",
                   value_name="level").dropna(subset=["level"])
    off_scale = sorted(set(long["level"]) - set(range(1, 6)))
    if off_scale:
        raise ValueError(f"{path.name}: levels {off_scale} are outside the rubric's 1-5 scale")
    # A path needs the same evaluator's rating of both interviews of the participant.
    pairs = (long.pivot_table(index=["capacidad", "participante", "evaluator"], columns="momento", values="level")
             .reindex(columns=list(STAGES)).dropna().astype(int).rename_axis(columns=None).reset_index())
    pairs["change"] = pairs["post"] - pairs["pre"]
    return pairs, humans


def output_path(summary: Path) -> Path:
    """results/figures/figure3_change_trajectories_YYYYMMDD.png, dated like the ratings summary it draws.
    Copied from figure1_baseline_condition.py."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"figure3_change_trajectories_{summary.name.split('_', 1)[0]}.png"


def draw_panel(ax: plt.Axes, pairs: pd.DataFrame) -> None:
    """Paths and level totals for one capacity."""
    paths = pairs.groupby(["pre", "post"]).size()
    # Thick paths first so thin ones stay visible on top.
    for (pre, post), n in paths.sort_values(ascending=False).items():
        ax.plot([0, 1], [pre, post], color=DIRECTIONS[(post > pre) - (post < pre)][1], linewidth=LINE_W * n,
                solid_capstyle="round", alpha=0.9, zorder=3)
    for x, stage, ha, offset in zip((0, 1), STAGES, ("right", "left"), (-0.16, 0.16)):
        for level, n in pairs[stage].value_counts().items():
            ax.scatter(x, level, s=DOT_AREA * n, color=MUTED, edgecolor="white", linewidth=0.4, zorder=4)
            ax.text(x + offset, level, str(n), ha=ha, va="center", fontsize=SMALL, color=MUTED)


def plot(pairs: pd.DataFrame, humans: list[str], summary: Path) -> None:
    caps = list(CAPACITIES)
    fig, axes = plt.subplots(1, len(caps), figsize=(WIDTH_CM * CM, HEIGHT_CM * CM), sharey=True, facecolor="white")
    for ax, cap in zip(axes, caps):
        ax.set_facecolor("white")
        draw_panel(ax, pairs[pairs["capacidad"] == cap])
        ax.set_xlim(-0.6, 1.6)
        ax.set_xticks([])
        ax.yaxis.grid(True, zorder=0, linewidth=0.5)
        ax.tick_params(axis="y", labelsize=FONT, pad=2)
        ax.text(0.5, 0.0, CAPACITIES[cap], transform=ax.transAxes, ha="center", va="top",
                fontsize=FONT, color=INK, linespacing=1.1)
    axes[0].set_ylim(0.5, 5.5)
    axes[0].set_yticks(range(1, 6), [RUBRIC_V5_NAMES[lv - 1] for lv in range(1, 6)])

    fig.subplots_adjust(left=LEFT, top=1 - HEADER_CM / HEIGHT_CM, bottom=BOTTOM_CM / HEIGHT_CM, wspace=0.08)
    # Title, caption and legend at the left edge of the whole chart: the level names.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in axes[0].get_yticklabels())
    x = fig.transFigure.inverted().transform((left, 0))[0]
    # Right margin as wide as the left one, so the chart sits centred on the page.
    fig.subplots_adjust(right=1 - x)
    fig.text(x, 1 - 0.15 / HEIGHT_CM, TITLE, ha="left", va="top", fontsize=TITLE_FONT, fontweight="bold", color=INK)
    fig.text(x, 1 - 0.55 / HEIGHT_CM, CAPTION, ha="left", va="top", fontsize=FONT, color=MUTED)

    # Two titled legends side by side at the foot of the figure, well below the capacity labels.
    style = dict(loc="lower left", fontsize=SMALL, title_fontsize=SMALL, alignment="left", handlelength=1.4,
                 handletextpad=0.6, columnspacing=0.9, borderaxespad=0, borderpad=0)
    kind = fig.legend(
        [Line2D([], [], color=color, linewidth=2.5, solid_capstyle="round") for _, color in DIRECTIONS.values()],
        [label for label, _ in DIRECTIONS.values()],
        title="Type of trajectory", ncol=len(DIRECTIONS), bbox_to_anchor=(x, 0.06 / HEIGHT_CM), **style)
    fig.canvas.draw()
    x2 = fig.transFigure.inverted().transform((kind.get_window_extent(renderer).x1, 0))[0] + LEGEND_GAP_CM / WIDTH_CM
    fig.legend(
        [Line2D([], [], color=MUTED, linewidth=LINE_W * n, solid_capstyle="round") for n in WIDTH_KEY],
        [str(n) for n in WIDTH_KEY],
        title="Quantity of trajectories", ncol=len(WIDTH_KEY), bbox_to_anchor=(x2, 0.06 / HEIGHT_CM), **style)

    out = output_path(summary)
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

    print(f"human evaluators {', '.join(humans)}: paths per capacity, pre (rows) x post (columns)")
    print(pairs.groupby(["capacidad", "pre", "post"]).size().unstack("post", fill_value=0).to_string())
    print("\npaths per evaluator:", pairs.groupby("evaluator").size().div(len(caps)).astype(int).to_dict())
    print(f"\n{TITLE}\n{CAPTION}")
    print("->", out.relative_to(OUT_DIR.parent.parent).as_posix(), f"({WIDTH_CM} x {HEIGHT_CM} cm)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to draw (default: the newest)")
    args = parser.parse_args()
    summary = latest_summary(args.date)
    plot(*load(summary), summary)
