"""Figure 12: averaged change trajectories by task performed during the workshops.

One row per task (construction, planting, logistics), one panel per capacity. For each transcript
(interview x capacity) the ratings of the human evaluators are averaged and rounded half down to a rubric
level (2.5 -> 2); each line joins a participant's averaged pre-workshop level to their averaged
post-workshop level.

Each row has two blocks of seven capacity panels: participants who did not take part in the row's task
(no, left) and those who did (yes, right). Line colour repeats the no / yes split; line thickness: number
of participants.
Dots at the ends, sized by count: participants of that panel's group at that level.

Inputs: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one unless
--date is given, and data/raw/participants_summary_tasks.xlsx (ID, participated_<task> = yes/no).
Output: results/figures/figure12_change_trajectories_by_tasks_YYYYMMDD.png (16 x 11.6 cm, 300 dpi).

Usage (from data_analysis/):
    python code/figure12_change_trajectories_by_tasks.py
    python code/figure12_change_trajectories_by_tasks.py --date 20261110
"""
import argparse
import io
import re
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon

from plot_shared_config import (
    CAPACITIES, INK, MUTED, OUT_DIR, ROOT, RUBRIC_V5_NAMES, STAGES, VERTICAL_SHEET, evaluator_columns,
    latest_summary, TIME, GRID
)

HUMAN = re.compile(r"H\d+")
TASKS_FILE = ROOT / "data" / "raw" / "participants_summary_tasks.xlsx"
# Column of the tasks file -> row title.
TASKS = {
    "participated_building": "Construction",
    "participated_planting": "Planting",
    "participated_logistics": "Logistics",
}
LINE_W = 0.5  # points of line width per participant
DOT_AREA = 3  # points^2 of dot area per participant
# Thickness legend: a wedge growing from a point to the width of a WEDGE_MAX-participant path, between
# the dots of a 1- and a WEDGE_MAX-participant level.
WEDGE_MAX = 10
WEDGE_CM, WEDGE_PAD_CM = 1.6, 0.15  # length of the wedge; space between it and its labels
WEDGE_LABELS = ("Fewer participants", "More participants")
LEGEND_TITLES = ("Participated in the task", "Line thickness and dot size, quantity of participants")

# Participation -> (label, colour), in block order from left to right; colours of the pre and post moments.
GROUPS = {"no": ("No", TIME["pre"][1]), "yes": ("Yes", TIME["post"][1])}

BLOCK_GAP = 0.6  # width of the space between the no and yes blocks, as a fraction of a panel's width
# Layout in cm, top to bottom: top margin, No / Yes block titles, three rows of panels (each
# under its row title and group sizes), capacity labels and legends.
WIDTH_CM, HEIGHT_CM, TOP_CM, BOTTOM_CM = 16, 11.6, 0.1, 2.0
GROUP_TITLE_CM = 0.75  # band between the top margin and the first row: block titles above the first row title
ROW_TITLE_CM = 0.12  # height of the row title above its row's panels
N_OFFSET_CM = -0.12  # height of the group sizes above the panels: just over the top gridline
ROW_GAP = 0.2  # space between rows, as a fraction of a row's height (holds the row title)
LEGEND_GAP_CM = 0.5  # horizontal space between the two legends
LEFT = 0.13  # first guess at the left edge of the panels; moved so the level names touch the margin
MARGIN_CM = 0.05  # space left and right of the chart
CM = 1 / 2.54
FONT, SMALL, TICK, TITLE_FONT = 6.5, 5.5, 6.5, 8  # points


def pid(x) -> str:
    """Participant IDs as three-digit strings ('1', 1, '001' -> '001')."""
    return str(int(float(x))).zfill(3)


def load(path: Path) -> tuple[pd.DataFrame, list[str]]:
    """Averaged human pre/post levels in long form (capacidad, participante, pre, post), one row per
    participant and capacity, joined to the yes/no task columns, and the human evaluators that rated
    at least one interview."""
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
    # Mean of the humans that rated each transcript, rounded to the nearest level, halves down (not Python's round-half-to-even).
    mean = long.groupby(["capacidad", "participante", "momento"])["level"].mean()
    rounded = np.ceil(mean - 0.5).astype(int).rename("level").reset_index()
    pairs = (rounded.pivot(index=["capacidad", "participante"], columns="momento", values="level")
             .reindex(columns=list(STAGES)).dropna().astype(int).rename_axis(columns=None).reset_index())
    pairs["participante"] = pairs["participante"].map(pid)

    tasks = pd.read_excel(TASKS_FILE)
    tasks["participante"] = tasks["ID"].map(pid)
    tasks = tasks[["participante", *TASKS]]
    for col in TASKS:
        tasks[col] = tasks[col].astype(str).str.strip().str.lower()
        unknown = sorted(set(tasks[col]) - set(GROUPS))
        if unknown:
            raise ValueError(f"{TASKS_FILE.name}, {col}: values {unknown} are not yes/no")
    only_one = sorted(set(pairs["participante"]) ^ set(tasks["participante"]))
    if only_one:
        print(f"Warning: participants in only one of the two files (left out): {only_one}")
    return pairs.merge(tasks, on="participante", how="inner"), humans


def output_path(summary: Path) -> Path:
    """results/figures/figure12_change_trajectories_by_tasks_YYYYMMDD.png, dated like the ratings summary."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUT_DIR / f"figure12_change_trajectories_by_tasks_{summary.name.split('_', 1)[0]}.png"


def draw_panel(ax: plt.Axes, pairs: pd.DataFrame, color: str) -> None:
    """Paths and level totals of one group (yes or no) for one capacity."""
    paths = pairs.groupby(["pre", "post"]).size()
    # Thick paths first so thin ones stay visible on top.
    for (pre, post), n in paths.sort_values(ascending=False).items():
        ax.plot([0, 1], [pre, post], color=color, linewidth=LINE_W * n,
                solid_capstyle="round", alpha=0.9, zorder=3)
    for x, stage in zip((0, 1), STAGES):
        for level, n in pairs[stage].value_counts().items():
            ax.scatter(x, level, s=DOT_AREA * n, color=MUTED, edgecolor="white", linewidth=0.4, zorder=4)


def plot(data: pd.DataFrame, humans: list[str], summary: Path) -> None:
    caps = list(CAPACITIES)
    groups = list(GROUPS)
    # Grid columns: the seven capacities of each group, with an empty spacer column between the blocks.
    ratios = ([1] * len(caps) + [BLOCK_GAP]) * len(groups)
    fig = plt.figure(figsize=(WIDTH_CM * CM, HEIGHT_CM * CM), facecolor="white")
    grid = fig.add_gridspec(len(TASKS), len(ratios) - 1, width_ratios=ratios[:-1], wspace=0, hspace=ROW_GAP)
    step = len(caps) + 1
    axes = np.empty((len(TASKS), len(groups) * len(caps)), dtype=object)
    for r, task in enumerate(TASKS):
        for g, group in enumerate(groups):
            for c, cap in enumerate(caps):
                ax = fig.add_subplot(grid[r, g * step + c], sharey=axes[0, 0])
                axes[r, g * len(caps) + c] = ax
                ax.set_facecolor("white")
                label, color = GROUPS[group]
                subset = data[(data["capacidad"] == cap) & (data[task] == group)]
                draw_panel(ax, subset, color)
                ax.set_xlim(-0.6, 1.6)
                ax.set_xticks([])
                ax.yaxis.grid(True, zorder=0, linewidth=0.5)
                ax.tick_params(axis="y", labelsize=TICK, pad=2)
                if c or g:
                    ax.tick_params(axis="y", labelleft=False)
    axes[0, 0].set_ylim(0.5, 5.5)
    axes[0, 0].set_yticks(range(1, 6), [RUBRIC_V5_NAMES[lv - 1] for lv in range(1, 6)])

    fig.subplots_adjust(left=LEFT, top=1 - (TOP_CM + GROUP_TITLE_CM) / HEIGHT_CM, bottom=BOTTOM_CM / HEIGHT_CM)
    # Row titles and legend at the left edge of the whole chart: the level names.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    left = min(t.get_window_extent(renderer).x0 for t in axes[0, 0].get_yticklabels())
    # Shift the panels left until the level names sit at the margin, and stretch them to the right margin.
    x = MARGIN_CM / WIDTH_CM
    fig.subplots_adjust(left=LEFT - fig.transFigure.inverted().transform((left, 0))[0] + x, right=1 - x)
    # Capacity names under each panel of the last row, turned 90° anticlockwise to fit the narrow panels;
    # the lines of a two-line name end flush against the panel.
    for ax, cap in zip(axes[-1], caps * len(groups)):
        box = ax.get_position()
        fig.text((box.x0 + box.x1) / 2, box.y0 - 0.05 / HEIGHT_CM, CAPACITIES[cap], ha="center", va="top",
                 rotation=90, multialignment="right", fontsize=FONT, color=INK, linespacing=1.1)

    # One No / Yes title per block, above the first row; in every row the task at the left edge and the
    # group sizes centred over each block. Group sizes are the same in every capacity panel of a row.
    people = data.drop_duplicates("participante")
    for r, (row, (task, name)) in enumerate(zip(axes, TASKS.items())):
        counts = people[task].value_counts()
        y = row[0].get_position().y1 + ROW_TITLE_CM / HEIGHT_CM
        title = fig.text(x, y, name, ha="left", va="bottom", fontsize=FONT, fontweight="bold", color=INK)
        if r:
            # Dashed divider through the vertical centre of the row title, across the panels, in the colour
            # and width of the gridlines.
            box = fig.transFigure.inverted().transform(title.get_window_extent(renderer))
            y_line = (box[0, 1] + box[1, 1]) / 2
            fig.add_artist(Line2D([row[0].get_position().x0, row[-1].get_position().x1], [y_line, y_line],
                                  transform=fig.transFigure, color=MUTED, linewidth=0.4, linestyle=(0, (4, 4))))
        for g, (group, (label, color)) in enumerate(GROUPS.items()):
            first, last = row[g * len(caps)].get_position(), row[(g + 1) * len(caps) - 1].get_position()
            centre = (first.x0 + last.x1) / 2
            fig.text(centre, row[0].get_position().y1 + N_OFFSET_CM / HEIGHT_CM, f"n = {counts.get(group, 0)}",
                     ha="center", va="bottom", fontsize=SMALL, color=color)
            if r == 0:
                fig.text(centre, y + 0.35 / HEIGHT_CM, label, ha="center", va="bottom", fontsize=TITLE_FONT,
                         color=color, fontweight="bold")

    # Two titled legends below the capacity labels, side by side from the left edge of the chart.
    style = dict(loc="lower left", fontsize=SMALL, title_fontsize=SMALL, alignment="left", handlelength=1.4,
                 handletextpad=0.6, columnspacing=0.9, borderaxespad=0, borderpad=0)
    kinds = fig.legend(
        [Line2D([], [], color=color, linewidth=2.5, solid_capstyle="round") for _, color in GROUPS.values()],
        [label for label, _ in GROUPS.values()],
        title=LEGEND_TITLES[0], bbox_to_anchor=(x, 0.06 / HEIGHT_CM), ncol=len(GROUPS), **style,
    )
    fig.canvas.draw()
    kinds.get_title().set_color(INK)
    to_fig = fig.transFigure.inverted()
    x_next = to_fig.transform((kinds.get_window_extent(renderer).x1, 0))[0] + LEGEND_GAP_CM / WIDTH_CM
    # Thickness key: a wedge from a hairline to the thickest path, between "fewer" and "more", aligned with
    # the title and the entry row of the colour legend.
    title_box = to_fig.transform(kinds.get_title().get_window_extent(renderer))
    row_box = to_fig.transform(kinds.get_texts()[0].get_window_extent(renderer))
    y_row = (row_box[0, 1] + row_box[1, 1]) / 2
    fig.text(x_next, title_box[0, 1], LEGEND_TITLES[1], ha="left", va="bottom", fontsize=SMALL, color=INK)
    fewer = fig.text(x_next, y_row, WEDGE_LABELS[0], ha="left", va="center", fontsize=SMALL, color=MUTED)
    pad = WEDGE_PAD_CM / WIDTH_CM

    def dot(x_left: float, n: int) -> float:
        """Dot of an n-participant level, as drawn in the panels, from x_left; returns its right edge."""
        size = np.sqrt(DOT_AREA * n)  # marker diameter in points
        radius = size / 2 / 72 / (WIDTH_CM * CM)
        fig.add_artist(Line2D([x_left + radius], [y_row], marker="o", markersize=size, color=MUTED,
                              markeredgecolor="white", markeredgewidth=0.4, transform=fig.transFigure))
        return x_left + 2 * radius

    # Fewer participants · small dot · wedge · large dot · More participants
    x0 = dot(to_fig.transform(fewer.get_window_extent(renderer))[1, 0] + pad, 1) + pad
    x1 = x0 + WEDGE_CM / WIDTH_CM
    half = LINE_W * WEDGE_MAX / 72 / (HEIGHT_CM * CM) / 2  # half the thickest path, in figure height
    fig.add_artist(Polygon([(x0, y_row), (x1, y_row + half), (x1, y_row - half)], closed=True,
                           transform=fig.transFigure, facecolor=MUTED, edgecolor="none"))
    x_more = dot(x1 + pad, WEDGE_MAX) + pad
    fig.text(x_more, y_row, WEDGE_LABELS[1], ha="left", va="center", fontsize=SMALL, color=MUTED)

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

    print(f"rounded mean of human evaluators {', '.join(humans)}")
    for task, name in TASKS.items():
        change = data.assign(change=data["post"] - data["pre"])
        print(f"\n{name}: mean change (post - pre) per capacity, by participation")
        print(change.pivot_table(index=task, columns="capacidad", values="change", aggfunc="mean")
              .reindex(columns=caps).round(2).to_string())
    print("->", out.relative_to(OUT_DIR.parent.parent).as_posix(), f"({WIDTH_CM} x {HEIGHT_CM} cm)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to draw (default: the newest)")
    args = parser.parse_args()
    summary = latest_summary(args.date)
    plot(*load(summary), summary)
