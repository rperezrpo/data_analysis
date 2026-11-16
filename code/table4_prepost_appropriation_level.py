"""Table 4: mean appropriation level before and after the workshops, by capacity.

Rows    = the seven evaluated capacities, sorted by mean change (largest first), plus "All capacities".
Columns = Pre, Post (mean level across participants), Change (Post - Pre) and Fell / Same / Rose
          (number of participants whose level went down / stayed / went up, post vs pre).

Level per interview and capacity = its 'human_average' column (the mean of the human evaluators who
rated it, written by data_compile_ratings.py), NOT rounded. "All capacities" = mean over every
participant x capacity. Only participants with both a pre and a post interview are counted.

Inputs: data/processed/YYYYMMDD_ratings_summary.xlsx (sheet 'results_vertical'), the newest one unless
--date is given.
Output: results/tables/table4_prepost_appropriation_level_YYYYMMDD.xlsx (sheets table4, notes), dated
like the ratings summary.

Usage (from data_analysis/):
    python code/table4_prepost_appropriation_level.py
    python code/table4_prepost_appropriation_level.py --date 20261110
"""
import argparse
import io
import time
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, Side

from plot_shared_config import CAPACITIES, ROOT, STAGES, TABLES_DIR, VERTICAL_SHEET, latest_summary

AVERAGE = "human_average"  # mean of the human evaluators per interview and capacity (data_compile_ratings.py)
CAPS = list(CAPACITIES)
# Capacity code -> label used in the paper.
LABELS = {
    "biobased_materials": "Recognise biobased materials",
    "community_participation": "Recognise community participation",
    "functions_vegetation": "Identify functions of vegetation",
    "nbs_definition": "Understand nature-based solutions",
    "climate_hazard": "Understand climate hazards",
    "identify_landslide": "Know early landslide signs",
    "local_hazard": "Identify local hazards",
}
TOTAL = "All capacities"
HEADER = ["Capacity", "Pre", "Post", "Change", "Fell / Same / Rose"]


def pid(x) -> str:
    """Participant IDs as three-digit strings ('1', 1, '001' -> '001')."""
    return str(int(float(x))).zfill(3)


def load_levels(path: Path) -> pd.DataFrame:
    """Pre and post level (columns) per participant and capacity (index), complete pairs only."""
    df = pd.read_excel(path, sheet_name=VERTICAL_SHEET, dtype={"participante": str})
    if AVERAGE not in df.columns:
        raise SystemExit(f"{path.name}: no '{AVERAGE}' column; rerun data_compile_ratings.py")
    df = df[df["capacidad"].isin(CAPS) & df["momento"].isin(STAGES)].copy()
    df["participante"] = df["participante"].map(pid)
    levels = df.pivot(index=["participante", "capacidad"], columns="momento", values=AVERAGE)
    incomplete = levels[levels[["pre", "post"]].isna().any(axis=1)]
    if len(incomplete):
        print(f"Warning: {len(incomplete)} participant x capacity pairs without pre or post (left out)")
    return levels[["pre", "post"]].dropna()


def build_table(levels: pd.DataFrame) -> pd.DataFrame:
    # Rounded to 4 decimals so that averages such as 2.9999999 count as no change.
    change = (levels["post"] - levels["pre"]).round(4)
    rows = []
    for cap, grp in levels.groupby(level="capacidad"):
        d = change.loc[grp.index]
        rows.append({
            "Capacity": LABELS.get(cap, cap),
            "Pre": grp["pre"].mean(),
            "Post": grp["post"].mean(),
            "Change": grp["post"].mean() - grp["pre"].mean(),
            "Fell": int((d < 0).sum()), "Same": int((d == 0).sum()), "Rose": int((d > 0).sum()),
        })
    table = pd.DataFrame(rows).sort_values("Change", ascending=False, ignore_index=True)
    table.loc[len(table)] = {
        "Capacity": TOTAL, "Pre": levels["pre"].mean(), "Post": levels["post"].mean(),
        "Change": levels["post"].mean() - levels["pre"].mean(),
    }
    return table.astype({"Fell": "Int64", "Same": "Int64", "Rose": "Int64"})


def write(table: pd.DataFrame, n: int, summary: Path, out: Path) -> None:
    caption = (f"Table 4. Mean appropriation level before and after the workshops, by capacity "
               f"(n = {n} participants)")
    notes = pd.DataFrame({"Note": [
        f"Level = '{AVERAGE}' (mean of the human evaluators per interview and capacity), not rounded.",
        "Pre / Post = mean level across participants; Change = Post - Pre.",
        "Fell / Same / Rose = participants whose level was lower / equal / higher after the workshops.",
        f"{TOTAL} = mean over every participant x capacity.",
        "Scale: 1 Absence, 2 Awareness, 3 Competence, 4 Expertise, 5 Leadership.",
        f"Source: {summary.name}",
    ]})

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as xl:
        notes.to_excel(xl, sheet_name="notes", index=False)
        ws = xl.book.create_sheet("table4", 0)
        thin = Side(style="thin", color="000000")
        box = Border(left=thin, right=thin, top=thin, bottom=thin)

        ws.append(HEADER)
        for _, r in table.iterrows():
            counts = "–" if pd.isna(r["Fell"]) else f"{int(r['Fell'])} / {int(r['Same'])} / {int(r['Rose'])}"
            ws.append([r["Capacity"], r["Pre"], r["Post"], r["Change"], counts])
        ws.append([caption])
        last = ws.max_row
        ws.merge_cells(start_row=last, start_column=1, end_row=last, end_column=len(HEADER))

        for row in ws.iter_rows(min_row=1, max_row=last, max_col=len(HEADER)):
            for cell in row:
                cell.border = box
                cell.font = Font(name="Calibri", size=11)
                if cell.column > 1:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
        for cell in ws[1]:
            cell.font = Font(name="Calibri", size=11, bold=True)
        for r in range(2, last):
            ws.cell(r, 2).number_format = ws.cell(r, 3).number_format = "0.00"
            ws.cell(r, 4).number_format = "+0.00;-0.00;0.00"
        cap_cell = ws.cell(last, 1)
        cap_cell.font = Font(name="Calibri", size=11, italic=True)
        cap_cell.alignment = Alignment(horizontal="center", vertical="center")

        for letter, w in {"A": 38, "B": 10, "C": 10, "D": 10, "E": 20}.items():
            ws.column_dimensions[letter].width = w
        for cell in xl.sheets["notes"][1]:
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
                raise
            time.sleep(0.5)


def main(date: str | None) -> None:
    summary = latest_summary(date)
    levels = load_levels(summary)
    n = levels.index.get_level_values("participante").nunique()
    table = build_table(levels)
    out = TABLES_DIR / f"table4_prepost_appropriation_level_{summary.name.split('_', 1)[0]}.xlsx"
    write(table, n, summary, out)

    print(table.round(2).to_string(index=False))
    print(f"\nn = {n} participants")
    print("->", out.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", help="YYYYMMDD of the ratings summary to use (default: the newest)")
    main(parser.parse_args().date)
