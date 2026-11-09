"""Shared configuration, data loading and drawing helpers for the capacity figures.

Used by plots_capabilities_analysis.py, plot_change_distribution.py and
plot_trajectories.py. Workbooks, level scales, capacity names and every colour
are defined here and nowhere else.

Two workbook formats are read:
- horizontal (overall_results_*.xlsx): one row per participant, pre_<capacity>
  and post_<capacity> columns, levels on the figures' 0-4 scale. From v6.1 on
  (results_v6.1.xlsx) the levels are on the rubric's 1-5 scale and each sheet
  ('Revisor', 'Mediana A1-A4') is an assessment of its own;
- vertical (results_v3.3.xlsx onwards): sheet 'results_vertical', one row per
  interview and capacity (codigo, participante, momento, capacidad) and one
  column per evaluator (H1, A1 ...), levels on the rubric's 1-5 scale. Each
  evaluator column is drawn as an assessment of its own.

Inputs and outputs follow the data_analysis/ layout: the ratings summary is
data/processed/YYYYMMDD_ratings_summary.xlsx (written by data_compile_ratings.py)
and figures go to results/figures/. Without arguments the scripts draw the
newest summary; --date YYYYMMDD, or the dated file name, picks a specific run.
Workbooks of earlier rounds are still found in code/source/ if kept there.
"""
import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import to_rgb

HERE = Path(__file__).resolve().parent  # data_analysis/code/
ROOT = HERE.parent  # data_analysis/
PROCESSED_DIR = ROOT / "data" / "processed"
TABLES_DIR = ROOT / "results" / "tables"
OUT_DIR = ROOT / "results" / "figures"
SOURCE_DIR = HERE / "source"  # workbooks of earlier rounds (overall_results_*, results_v*), if kept
# Where a workbook named without a folder is looked for, in order.
SEARCH_DIRS = (PROCESSED_DIR, TABLES_DIR, SOURCE_DIR, SOURCE_DIR / "overall", HERE)

# Outputs of data_compile_ratings.py and data_reliability_analysis.py, written as YYYYMMDD_<name>.
SUMMARY_NAME = "ratings_summary.xlsx"
RELIABILITY_NAME = "reliability_results.xlsx"
DATE_PREFIX = re.compile(r"(\d{8})_(.+)")

VERTICAL_SHEET = "results_vertical"
RUBRIC_OFFSET = 1  # vertical workbooks store the rubric's 1-5 levels; figures use 0-4
# Evaluator columns: H1, A1 ... in vertical workbooks, "Evaluador ..." in the reviewer matrices.
EVALUATOR_COLUMN = re.compile(r"[HA]\d+|evaluador.*", re.IGNORECASE)
PANEL_COLUMN = "panel"  # consensus of the LLM agents, derived on reading (see read_vertical)

# Level -> (label, fill colour), on the 0-4 scale. Level 0 is the rubric's level 1, below Weak.
LEVELS = {
    0: ("Lacks", "#b0aea6"),
    1: ("Weak", "#f06085"),
    2: ("Basic", "#f0c960"),
    3: ("Moderate", "#60f070"),
    4: ("Strong", "#6080f0"),
}

# Interview moment -> (label, colour), for pre/post comparisons; keys as in STAGES and 'momento'.
TIME = {
    "pre": ("Pre-workshop", "#dda15e"),
    "post": ("Post-workshop", "#7b2cbf"),
}

# Level names from rubric v5 on (columns 1_absence ... 5_leadership), on the 0-4 scale.
RUBRIC_V5_NAMES = {0: "Absence", 1: "Awareness", 2: "Competence", 3: "Expertise", 4: "Leadership"}
FOUR_LEVELS = (1, 2, 3, 4)
FIVE_LEVELS = (0, 1, 2, 3, 4)
# Levels drawn below the zero line in the levels figure, from the line outwards.
LEVELS_BELOW = (1, 0)


@dataclass(frozen=True)
class Workbook:
    file: str
    title: str
    suffix: str  # appended to output file names
    levels: tuple[int, ...]  # the rubric's scale; scores outside it are rejected
    evaluator: str | None = None  # evaluator column of a vertical workbook; None for a horizontal one
    sheet: str | None = None  # sheet of a horizontal workbook; None for 'horizontal' or the first sheet
    offset: int = 0  # subtracted from a horizontal workbook's scores to reach the 0-4 scale
    names: dict[int, str] | None = None  # level names of its rubric; None for those in LEVELS

    @property
    def path(self) -> Path:
        return locate(self.file)

    @property
    def level_styles(self) -> dict[int, tuple[str, str]]:
        """Level -> (label, fill colour), with the names of this workbook's rubric."""
        return {lv: ((self.names or {}).get(lv, label), color) for lv, (label, color) in LEVELS.items()}


VERTICAL_VERSIONS = ("v3.3", "v4.1")  # source/results_<version>.xlsx
WORKBOOKS = [
    Workbook("overall_results_v1.xlsx", "Human assessment", "", FOUR_LEVELS),
    Workbook("overall_results_LLM.xlsx", "LLM-as-judge assessment", "_LLM", FOUR_LEVELS),
    Workbook("overall_results_LLM_v2.xlsx", "LLM-as-judge assessment (v2)", "_LLM_v2", FIVE_LEVELS),
]
for v in VERTICAL_VERSIONS:
    WORKBOOKS.append(Workbook(f"results_{v}.xlsx", f"Human assessment ({v})", f"_{v}_H1", FIVE_LEVELS, "H1"))
    WORKBOOKS += [
        Workbook(f"results_{v}.xlsx", f"LLM-as-judge assessment, agent {a} ({v})", f"_{v}_{a}", FIVE_LEVELS, a)
        for a in ("A1", "A2", "A3", "A4")
    ]
    WORKBOOKS.append(Workbook(
        f"results_{v}.xlsx", f"LLM panel consensus: low median of A1–A4 ({v})", f"_{v}_{PANEL_COLUMN}", FIVE_LEVELS, PANEL_COLUMN,
    ))
WORKBOOKS += [
    Workbook("results_v6.1.xlsx", "LLM-as-judge assessment, reviewer (v6.1)", "_v6.1_reviewer", FIVE_LEVELS,
             sheet="Revisor", offset=RUBRIC_OFFSET, names=RUBRIC_V5_NAMES),
    Workbook("results_v6.1.xlsx", "LLM panel consensus: median of A1–A4 (v6.1)", "_v6.1_median", FIVE_LEVELS,
             sheet="Mediana A1-A4", offset=RUBRIC_OFFSET, names=RUBRIC_V5_NAMES),
]

CAPACITIES = {
    "nbs_definition": "NbS\ndefinition",
    "climate_hazard": "Climate\nhazard",
    "local_hazard": "Local\nhazard",
    "identify_landslide": "Identify\nlandslide",
    "functions_vegetation": "Functions of\nvegetation",
    "biobased_materials": "Benefits of\nbio-based",
    "community_participation": "Community\nparticipation",
}
# Column names used by older workbooks -> current capacity key.
ALIASES = {"sbn_definition": "nbs_definition", "benefits_biobased": "biobased_materials"}
STAGES = ("pre", "post")

LEGEND_TITLE = "Appropriation level of the capacity"

# Change in level (post minus pre) -> colour. Drops darken in orange, gains in blue.
_CHANGE_COLORS = {
    -4: "#7a2c0e", -3: "#7a2c0e", -2: "#b3441a", -1: "#eb6834",
    0: "#b0aea6",
    1: "#86b6ef", 2: "#3987e5", 3: "#1c5cab", 4: "#0d366b",
}


def _change_label(change: int) -> str:
    if change == 0:
        return "No change"
    sign = "+" if change > 0 else "−"
    return f"{sign}{abs(change)} level{'s' if abs(change) > 1 else ''}"


# Change score -> (label, colour), for every change the five-level scale allows.
CHANGES = {change: (_change_label(change), color) for change, color in _CHANGE_COLORS.items()}

# The only non-data colours; everything else inherits them through rcParams.
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e1e0d9"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
    "font.size": 9,
    "text.color": INK,
    "axes.labelcolor": MUTED,
    "xtick.labelcolor": MUTED,
    "ytick.labelcolor": MUTED,
    "legend.labelcolor": MUTED,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.spines.bottom": False,
    "axes.axisbelow": True,
    "xtick.bottom": False,
    "ytick.left": False,
    "legend.frameon": False,
    "savefig.dpi": 300,
})


# --- data -------------------------------------------------------------------

def dated_files(name: str, folder: Path = PROCESSED_DIR) -> dict[str, Path]:
    """Date (YYYYMMDD) -> path of every YYYYMMDD_<name> in folder, oldest first."""
    found = {}
    for path in sorted(folder.glob(f"*_{name}")):
        match = DATE_PREFIX.fullmatch(path.name)
        if match and match.group(2) == name:
            found[match.group(1)] = path
    return found


def dated(name: str, folder: Path = PROCESSED_DIR, date: str | None = None) -> Path:
    """YYYYMMDD_<name> in folder: the one of `date` if given, else the newest."""
    found = dated_files(name, folder)
    if date:
        if date not in found:
            raise SystemExit(f"No {date}_{name} in {folder}. Available dates: {', '.join(found) or 'none'}")
        return found[date]
    if not found:
        raise SystemExit(f"No YYYYMMDD_{name} in {folder}; run the data_*.py scripts first")
    return found[max(found)]


def latest_summary(date: str | None = None) -> Path:
    """The ratings summary of `date` (YYYYMMDD), or the newest one."""
    return dated(SUMMARY_NAME, PROCESSED_DIR, date)


def latest_reliability(date: str | None = None) -> Path:
    """The reliability results of `date` (YYYYMMDD), or the newest ones."""
    return dated(RELIABILITY_NAME, TABLES_DIR, date)


def run_date(path: Path) -> str | None:
    """'2026-11-06' for a file named 20261106_..., else None."""
    match = DATE_PREFIX.fullmatch(Path(path).name)
    return f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}" if match else None


def locate(file: str | Path) -> Path:
    """Path of a workbook: as given if it exists, else the first of SEARCH_DIRS that holds it.

    A name without a date prefix (ratings_summary.xlsx) that only exists dated
    resolves to the newest YYYYMMDD_<name>; give the dated name for a specific run.
    """
    file = Path(file)
    if file.exists():
        return file
    for d in SEARCH_DIRS:
        if (d / file.name).exists():
            return d / file.name
    for d in SEARCH_DIRS:
        found = dated_files(file.name, d) if d.is_dir() else {}
        if found:
            return found[max(found)]
    raise SystemExit(f"{file.name} not found in {', '.join(str(d) for d in SEARCH_DIRS)}")


def is_vertical(path: Path) -> bool:
    return VERTICAL_SHEET in pd.ExcelFile(path).sheet_names


def evaluator_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if EVALUATOR_COLUMN.fullmatch(str(c))]


def low_median(row: pd.Series) -> float:
    """Median that, for an even count, takes the lower middle value, so it is always a score some agent gave."""
    values = row.dropna().sort_values()
    return values.iloc[(len(values) - 1) // 2] if len(values) else float("nan")


def read_vertical(path: Path) -> pd.DataFrame:
    """The 'results_vertical' sheet with every evaluator column shifted to the 0-4 scale.

    Adds PANEL_COLUMN, the low median of the agents (A1 ...). It is not an
    evaluator column, so the evaluator figures leave it out.
    """
    # Codes keep their leading zeros ("001") only if read as text.
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET, dtype={"participante": str, "codigo": str})
    evaluators = evaluator_columns(df)
    df[evaluators] = df[evaluators].apply(pd.to_numeric) - RUBRIC_OFFSET
    agents = [c for c in evaluators if re.fullmatch(r"A\d+", str(c))]
    if agents:
        df[PANEL_COLUMN] = df[agents].apply(low_median, axis=1)
    return df


def resolve(name: str) -> list[Workbook]:
    """Workbooks for a file name, optionally narrowed to one evaluator as 'file.xlsx:A1'.

    Registered workbooks come first; an unknown vertical file gives one workbook
    per evaluator column, an unknown horizontal file is read on the five-level scale.
    """
    spec, sep, evaluator = name.rpartition(":")
    if not sep or not spec or re.search(r"[\\/]", evaluator):
        spec, evaluator = name, ""
    file, stem = Path(spec).name, Path(spec).stem
    registered = [wb for wb in WORKBOOKS if wb.file == file and evaluator in ("", wb.evaluator)]
    if registered:
        return registered
    path = locate(spec)
    if not is_vertical(path):
        return [Workbook(str(path), stem, f"_{stem}", FIVE_LEVELS)]
    if evaluator:
        columns = [evaluator]
    else:
        # Evaluators without a single rating yet (an empty rater folder) are left out.
        sheet = pd.read_excel(path, sheet_name=VERTICAL_SHEET)
        columns = [c for c in evaluator_columns(sheet) if sheet[c].notna().any()]
    return [vertical_workbook(path, ev) for ev in columns]


def vertical_workbook(path: Path, evaluator: str) -> Workbook:
    """One evaluator column of a vertical workbook; a dated ratings summary gets a readable title."""
    when = run_date(path)
    if not when:
        return Workbook(str(path), f"{path.stem}, {evaluator}", f"_{path.stem}_{evaluator}", FIVE_LEVELS, evaluator)
    tag = path.name.split("_", 1)[0]
    if re.fullmatch(r"A\d+", evaluator):
        who = f"LLM-as-judge assessment, agent {evaluator}"
    elif evaluator == PANEL_COLUMN:
        who = "LLM panel consensus: low median of the agents"
    else:
        who = f"Human assessment, evaluator {evaluator}"
    return Workbook(str(path), f"{who} (ratings of {when})", f"_{tag}_{evaluator}", FIVE_LEVELS, evaluator)


def default_workbooks(date: str | None = None) -> list[Workbook]:
    """Every rated evaluator of the ratings summary of `date`, or of the newest one."""
    return resolve(str(latest_summary(date)))


def workbooks_from_cli(description: str) -> tuple[list[Workbook], bool]:
    """Workbooks named on the command line, or those of the ratings summary (--date, default newest).

    The flag is True when workbooks were named explicitly.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("workbooks", nargs="*",
                        help="workbook.xlsx[:evaluator] (default: every evaluator of the ratings summary)")
    parser.add_argument("--date", help=f"YYYYMMDD of the {SUMMARY_NAME} to draw (default: the newest)")
    args = parser.parse_args()
    if args.workbooks:
        if args.date:
            parser.error("give either workbooks or --date, not both")
        return [wb for name in args.workbooks for wb in resolve(name)], True
    return default_workbooks(args.date), False


def _horizontal_scores(path: Path, sheet: str | None = None, offset: int = 0) -> pd.DataFrame:
    sheets = pd.ExcelFile(path).sheet_names
    sheet = sheet or ("horizontal" if "horizontal" in sheets else sheets[0])
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    # The table does not start at A1: locate the header row by its 'id' cell.
    header = raw.index[raw.eq("id").any(axis=1)][0]
    df = raw.iloc[header + 1:].set_axis(raw.iloc[header], axis=1)
    df = df.rename(columns=lambda c: next(
        (c.replace(old, new) for old, new in ALIASES.items() if str(c).endswith(old)), c
    ))
    return pd.concat(
        pd.DataFrame({
            "id": df["id"],
            "capacity": cap,
            "pre": pd.to_numeric(df[f"pre_{cap}"]) - offset,
            "post": pd.to_numeric(df[f"post_{cap}"]) - offset,
        })
        for cap in CAPACITIES
    ).reset_index(drop=True)


def _vertical_scores(path: Path, evaluator: str) -> pd.DataFrame:
    df = read_vertical(path)
    df = df[df["capacidad"].isin(CAPACITIES)]
    wide = df.pivot(index=["participante", "capacidad"], columns="momento", values=evaluator)
    return (
        wide.reindex(columns=list(STAGES)).rename_axis(columns=None).reset_index()
        .rename(columns={"participante": "id", "capacidad": "capacity"})
    )


def load_scores(wb: Workbook) -> pd.DataFrame:
    """One row per participant and capacity: id, capacity, pre, post, change.

    A missing score stays NaN, so a participant with only one of the two still
    counts for that stage. Change is post minus pre; the workbook's own
    change_* columns are not used.
    """
    scores = (
        _vertical_scores(wb.path, wb.evaluator) if wb.evaluator
        else _horizontal_scores(wb.path, wb.sheet, wb.offset)
    )

    values = scores[list(STAGES)].stack()
    off_scale = sorted(set(values) - set(wb.levels))
    if off_scale:
        raise ValueError(f"{wb.file}: scores {off_scale} are outside its scale {wb.levels}")
    scores["change"] = scores["post"] - scores["pre"]
    return scores


def load_paired(wb: Workbook) -> pd.DataFrame:
    """load_scores restricted to participants with both a pre and a post score, as integers."""
    paired = load_scores(wb).dropna(subset=["pre", "post"])
    return paired.astype({"pre": int, "post": int, "change": int}).reset_index(drop=True)


# --- drawing ----------------------------------------------------------------

def label_ink(fill: str) -> str:
    """Black or white, whichever reads on the given fill."""
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in to_rgb(fill))
    return "white" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.25 else INK


def draw_diverging_bar(ax: plt.Axes, x: float, row: pd.Series, below, above, styles, width: float) -> None:
    """One stack around the zero line; each segment is labelled with its share of the bar.

    `below` and `above` list the categories from the zero line outwards; `styles`
    maps a category to (label, colour).
    """
    total = row.sum()
    for direction, categories in ((-1, below), (1, above)):
        edge = 0
        for category in categories:
            n = int(row.get(category, 0))
            if n == 0:
                continue
            color = styles[category][1]
            ax.bar(x, direction * n, width, bottom=edge, color=color, edgecolor="white", linewidth=1.5, zorder=3)
            # Round half up, so 2 of 16 reads 13% rather than 12%.
            ax.text(
                x, edge + direction * n / 2, f"{int(100 * n / total + 0.5)}%",
                ha="center", va="center", color=label_ink(color), zorder=4,
            )
            edge += direction * n


def style_count_axis(ax: plt.Axes, ymax: int) -> None:
    """Symmetric participant axis around the zero line, with the capacities named underneath."""
    ax.set_ylim(-ymax - 0.5, ymax + 0.5)
    ticks = range(-ymax, ymax + 1, 4)
    ax.set_yticks(ticks, [abs(t) for t in ticks])
    ax.set_ylabel("Participants", fontsize=10)
    ax.set_xticks([])
    ax.set_xlim(-0.6, len(CAPACITIES) - 0.4)
    ax.yaxis.grid(True, zorder=0)
    ax.axhline(0, color=MUTED, linewidth=1.0, zorder=5)
    for i, label in enumerate(CAPACITIES.values()):
        ax.text(i, -0.03, label, ha="center", va="top", fontsize=10, transform=ax.get_xaxis_transform())


def swatch_legend(ax: plt.Axes, styles, categories, title: str) -> None:
    """Row of colour swatches above the plot for the given categories."""
    ax.legend(
        [plt.Rectangle((0, 0), 1, 1, color=styles[c][1]) for c in categories],
        [styles[c][0] for c in categories],
        title=title, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=len(categories),
        handlelength=1.2, handleheight=1.0, columnspacing=1.6, alignment="left",
    )


def add_header(fig: plt.Figure, title: str, subtitle: str, x: float = 0.07) -> None:
    fig.text(x, 0.965, title, ha="left", va="top", fontsize=15, fontweight="bold")
    fig.text(x, 0.92, subtitle, ha="left", va="top", fontsize=10, color=MUTED)


def save(fig: plt.Figure, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / name)
    plt.close(fig)
    print(f"-> {OUT_DIR.relative_to(ROOT).as_posix()}/{name}")
