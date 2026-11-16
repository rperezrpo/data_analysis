"""Table 5: learning by tasks. Mean change in appropriation level (post - pre) by task performed during the workshops.

Rows    = one per value of every column of participants_summary_tasks.xlsx except ID (e.g.
          participated_building = no / yes), with the number of participants (n) and their IDs.
Columns = the seven evaluated capacities, plus "All" (each participant's mean change across the
          seven capacities, averaged within the row).

Level per interview and capacity = its 'human_average' column (the mean of the human evaluators who
rated it, written by data_compile_ratings.py), rounded to the nearest level with an exact half rounded
down (2.5 -> 2, 2.67 -> 3). Attribute values are stripped, and yes/no columns lower-cased, so 'Yes ' and
'yes' are one row. Days assisted of 3 or more are pooled into one '3+' row (TOP_CODED).

Inputs: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one unless
--date is given, and data/raw/participants_summary_tasks.xlsx.
Output: results/tables/figure5_learning_by_tasks_YYYYMMDD.xlsx (sheets matrix, per_participant, notes),
dated like the ratings summary.

Usage (from data_analysis/):
    python code/figure5_learning_by_tasks.py
    python code/figure5_learning_by_tasks.py --date 20261110
"""
import argparse
import io
import time
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from plot_shared_config import CAPACITIES, ROOT, STAGES, TABLES_DIR, VERTICAL_SHEET, latest_summary

AVERAGE = "human_average"  # mean of the human evaluators per interview and capacity (data_compile_ratings.py)
TASKS_FILE = ROOT / "data" / "raw" / "participants_summary_tasks.xlsx"
CAPS = list(CAPACITIES)
VALUE_COLUMNS = [*CAPS, "All"]
# Numeric attribute -> value from which participants are pooled into one "<value>+" row (too few to show apart).
TOP_CODED = {"Days assisted": 3}


def pid(x) -> str:
    """Participant IDs as three-digit strings ('1', 1, '001' -> '001')."""
    return str(int(float(x))).zfill(3)


def round_half_down(values: pd.Series) -> pd.Series:
    """Nearest whole level, with an exact half going to the lower level (2.5 -> 2, 2.67 -> 3, 2.33 -> 2)."""
    return np.ceil(values - 0.5).astype(int)


def load_change(path: Path) -> pd.DataFrame:
    """Change in level (post - pre) per participant (index) and capacity (columns), plus 'All'."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET, dtype={"participante": str})
    if AVERAGE not in df.columns:
        raise SystemExit(f"{path.name}: no '{AVERAGE}' column; rerun data_compile_ratings.py")
    df = df[df["capacidad"].isin(CAPS) & df["momento"].isin(STAGES)].copy()
    df["participante"] = df["participante"].map(pid)
    df["level"] = round_half_down(df[AVERAGE])
    levels = df.pivot(index=["participante", "capacidad"], columns="momento", values="level")
    change = (levels["post"] - levels["pre"]).unstack("capacidad")[CAPS]
    change["All"] = change[CAPS].mean(axis=1)
    return change


def load_attributes() -> pd.DataFrame:
    """Participant attributes indexed by ID; text values stripped, yes/no columns lower-cased."""
    attrs = pd.read_excel(TASKS_FILE)
    attrs["ID"] = attrs["ID"].map(pid)
    attrs = attrs.set_index("ID")
    for col in attrs.columns:
        if attrs[col].dtype == object:
            attrs[col] = attrs[col].astype(str).str.strip()
            if set(attrs[col].str.lower()) <= {"yes", "no"}:
                attrs[col] = attrs[col].str.lower()
    for col, top in TOP_CODED.items():
        days = attrs[col].astype(int)
        attrs[col] = days.astype(str).where(days < top, f"{top}+")
    return attrs


def build_matrix(data: pd.DataFrame, attributes: list[str]) -> pd.DataFrame:
    rows = []
    for col in attributes:
        for value, group in data.groupby(col, sort=True):
            row: dict = {"Attribute": col, "Value": value, "n": len(group)}
            row.update(group[VALUE_COLUMNS].mean().to_dict())
            row["Participants"] = ", ".join(group.index)
            rows.append(row)
    return pd.DataFrame(rows)


def write(matrix: pd.DataFrame, per_participant: pd.DataFrame, summary: Path, out: Path) -> None:
    notes = pd.DataFrame({"Note": [
        "Cell = mean change in capacity level (post - pre) of the participants in that row.",
        f"Level = '{AVERAGE}' (mean of the human evaluators), rounded to nearest level, halves rounded down.",
        "All = each participant's mean change across the seven capacities, averaged within the row.",
        *[f"{col}: values of {top} or more pooled into '{top}+'." for col, top in TOP_CODED.items()],
        "Scale: 1 Absence, 2 Awareness, 3 Competence, 4 Expertise, 5 Leadership.",
        f"Sources: {summary.name}; {TASKS_FILE.name}",
    ]})
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as xl:
        matrix.to_excel(xl, sheet_name="matrix", index=False)
        per_participant.to_excel(xl, sheet_name="per_participant", index=False)
        notes.to_excel(xl, sheet_name="notes", index=False)

        ws = xl.sheets["matrix"]
        header = [c.value for c in ws[1]]
        first = header.index(CAPS[0]) + 1
        last = header.index("All") + 1
        for r in range(2, ws.max_row + 1):
            for c in range(first, last + 1):
                ws.cell(r, c).number_format = "+0.00;-0.00;0.00"
        rng = f"{get_column_letter(first)}2:{get_column_letter(last)}{ws.max_row}"
        ws.conditional_formatting.add(rng, ColorScaleRule(
            start_type="num", start_value=-1, start_color="F8696B",
            mid_type="num", mid_value=0, mid_color="FFFFFF",
            end_type="num", end_value=2, end_color="63BE7B"))
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        for letter, w in {"A": 24, "B": 10, "C": 5}.items():
            ws.column_dimensions[letter].width = w
        for c in range(first, last + 1):
            ws.column_dimensions[get_column_letter(c)].width = 14
        ws.column_dimensions[get_column_letter(last + 1)].width = 45
        ws.freeze_panes = ws.cell(2, first)

        for name in ("per_participant", "notes"):
            for cell in xl.sheets[name][1]:
                cell.font = Font(bold=True)
        xl.sheets["notes"].column_dimensions["A"].width = 100

    # OneDrive briefly locks a file it is syncing, so the write is retried.
    out.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(10):
        try:
            out.write_bytes(buffer.getvalue())
            break
        except OSError:
            if attempt == 9:
                raise SystemExit(f"Cannot write {out.relative_to(ROOT).as_posix()}: it is open in another "
                                 "program (Excel?). Close it and run the script again.")
            time.sleep(0.5)


def main(date: str | None) -> None:
    summary = latest_summary(date)
    change = load_change(summary)
    attrs = load_attributes()
    only_one = sorted(set(attrs.index) ^ set(change.index))
    if only_one:
        print(f"Warning: participants in only one of the two files (left out): {only_one}")
    data = attrs.join(change, how="inner")
    data.index.name = "ID"

    matrix = build_matrix(data, list(attrs.columns))
    out = TABLES_DIR / f"table5_learning_by_tasks_{summary.name.split('_', 1)[0]}.xlsx"
    write(matrix, data.reset_index(), summary, out)

    print(matrix.drop(columns="Participants").round(2).to_string(index=False))
    print(f"\n{len(matrix)} rows x {len(VALUE_COLUMNS)} value columns, {len(data)} participants")
    print("->", out.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to use (default: the newest)")
    main(parser.parse_args().date)
