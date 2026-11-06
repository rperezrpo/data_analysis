"""Compile the raw ratings of the LLM agents and the human evaluators into one workbook.

Necessary folder layout:

    data_analysis/
        code/01_compile_ratings.py
        data/raw/
            keys/
                resultados_v6.1_key.json          blind code (LLM run)  -> transcript
                clave_evaluacion_externa_v6.xlsx  blind code (humans)   -> transcript
            A1_<model>/E01.json ... E32.json      one JSON per interview (LLM agent)
            H1_<name>/E01_evaluacion_<name>.xlsx  one workbook per interview (human)
            ...
        data/processed/ratings_summary.xlsx       written by this script

Every folder in data/raw/ named <A|H><number>_<label> is one evaluator; the
prefix (A1, H2 ...) becomes its column in the summary. Agents (A) and humans (H)
read the transcripts under different blind codes, so each kind is mapped to the
transcript through its own key (KEYS below). Ratings are on the rubric's 1-5
scale (1 Absence, 2 Awareness, 3 Competence, 4 Expertise, 5 Leadership).

Output: data/processed/ratings_summary.xlsx, with the sheets
    results_vertical  one row per interview and capacity, one column per evaluator
    evaluators        what was read from each evaluator folder
    key               transcript, participant, moment and both blind codes

Usage (from data_analysis/; paths do not depend on the working directory):
    python code/01_compile_ratings.py
    python code/01_compile_ratings.py --source other/folder --out other_summary.xlsx
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent  # data_analysis/
SOURCE_DIR = ROOT / "data" / "raw"
OUT_FILE = ROOT / "data" / "processed" / "ratings_summary.xlsx"

# Evaluator kind -> key file (relative to the source folder) that maps its blind codes to transcripts.
KEYS = {
    "A": "keys/resultados_v6.1_key.json",
    "H": "keys/clave_evaluacion_externa_v6.xlsx",
}

CAPACITIES = (
    "nbs_definition",
    "climate_hazard",
    "local_hazard",
    "identify_landslide",
    "functions_vegetation",
    "biobased_materials",
    "community_participation",
)
LEVELS = range(1, 6)
MOMENTS = ("pre", "post")

# Columns always written, in this order, even when the folder is missing or holds no ratings yet.
EXPECTED_EVALUATORS = ("H1", "H2", "H3", "H4", "A1", "A2")

EVALUATOR_DIR = re.compile(r"(?P<kind>[AH])(?P<number>\d+)_(?P<label>.+)")
CODE = re.compile(r"E\d{2}")
TRANSCRIPT = re.compile(r"(?P<participant>\d{3})_(?P<moment>pre|post)")

warnings: list[str] = []


def warn(message: str) -> None:
    warnings.append(message)
    print(f"  WARNING: {message}", file=sys.stderr)


# --- keys --------------------------------------------------------------------

def read_key(path: Path) -> dict[str, str]:
    """Blind code (E01 ...) -> transcript ('013_pre'), from a JSON or an Excel key."""
    if path.suffix == ".json":
        key = json.loads(path.read_text(encoding="utf-8"))
    else:
        df = pd.read_excel(path, sheet_name="clave", dtype=str)
        key = dict(zip(df["codigo"].str.strip(), df["transcripcion"].str.strip()))
    for code, transcript in key.items():
        if not CODE.fullmatch(code) or not TRANSCRIPT.fullmatch(transcript):
            raise ValueError(f"{path.name}: unexpected entry {code!r} -> {transcript!r}")
    if len(set(key.values())) != len(key):
        raise ValueError(f"{path.name}: two codes point to the same transcript")
    return key


# --- readers -----------------------------------------------------------------

def parse_level(value, where: str) -> float:
    """A rubric level 1-5 as a number; blank -> NaN; anything else -> NaN with a warning."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return float("nan")
    text = str(value).strip()
    match = re.fullmatch(r"([1-5])(?:\.0+)?", text)
    if not match:
        warn(f"{where}: '{text}' is not a level 1-5; left blank")
        return float("nan")
    return float(match.group(1))


def read_agent_file(path: Path) -> dict[str, float]:
    """Capacity -> level from one LLM agent JSON ('capacidades': [{slug, nivel, ...}])."""
    data = json.loads(path.read_text(encoding="utf-8"))
    model = data.get("_modelo", {})
    if model and not model.get("ok", True):
        warn(f"{path.parent.name}/{path.name}: the run is flagged as not ok (_modelo.ok = false)")
    return {c["slug"]: parse_level(c.get("nivel"), f"{path.parent.name}/{path.name} [{c['slug']}]")
            for c in data["capacidades"]}


def read_human_file(path: Path) -> dict[str, float]:
    """Capacity -> level from one human matrix (columns 'slug' and 'valor_asignado')."""
    ws = load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    header_row = next((i for i, r in enumerate(rows) if "slug" in r and "valor_asignado" in r), None)
    if header_row is None:
        raise ValueError(f"{path.name}: no header row with 'slug' and 'valor_asignado'")
    header = rows[header_row]
    slug_col, value_col = header.index("slug"), header.index("valor_asignado")
    return {str(r[slug_col]).strip(): parse_level(r[value_col], f"{path.parent.name}/{path.name} [{r[slug_col]}]")
            for r in rows[header_row + 1:] if r[slug_col] not in (None, "")}


READERS = {"A": (read_agent_file, "*.json"), "H": (read_human_file, "*.xlsx")}


def read_evaluator(folder: Path, kind: str, key: dict[str, str]) -> tuple[dict, dict]:
    """(transcript, capacity) -> level for one evaluator folder, and a summary of what was read."""
    reader, pattern = READERS[kind]
    ratings: dict[tuple[str, str], float] = {}
    files = [p for p in sorted(folder.glob(pattern)) if not p.name.startswith("~$")]  # skip Excel lock files
    seen: dict[str, Path] = {}
    for path in files:
        match = CODE.match(path.stem)
        if not match:
            warn(f"{folder.name}/{path.name}: file name does not start with a code E01-E32; skipped")
            continue
        code = match.group()
        if code in seen:
            raise ValueError(f"{folder.name}: {seen[code].name} and {path.name} are both {code}")
        seen[code] = path
        if code not in key:
            warn(f"{folder.name}/{path.name}: {code} is not in the key; skipped")
            continue
        try:
            levels = reader(path)
        except Exception as error:  # unreadable or malformed file: leave its ratings blank
            warn(f"{folder.name}/{path.name}: could not be read ({error}); left blank")
            continue
        unknown = set(levels) - set(CAPACITIES)
        if unknown:
            warn(f"{folder.name}/{path.name}: unknown capacities {sorted(unknown)}; ignored")
        for capacity in CAPACITIES:
            if capacity not in levels:
                warn(f"{folder.name}/{path.name}: capacity '{capacity}' missing")
            ratings[(key[code], capacity)] = levels.get(capacity, float("nan"))
    missing_codes = sorted(set(key) - set(seen))
    filled = sum(1 for v in ratings.values() if not pd.isna(v))
    summary = {
        "files_read": len(seen),
        "codes_without_file": ", ".join(missing_codes),
        "ratings_filled": filled,
        "ratings_expected": len(key) * len(CAPACITIES),
    }
    return ratings, summary


# --- compile -----------------------------------------------------------------

def compile_ratings(source: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    keys = {kind: read_key(source / file) for kind, file in KEYS.items()}
    transcripts = set(keys["A"].values())
    for kind, key in keys.items():
        if set(key.values()) != transcripts:
            raise ValueError(f"the keys of kinds A and {kind} do not cover the same transcripts")

    # Match each folder name once; non-evaluator folders (e.g. keys/) are skipped.
    matched = [(p, m) for p in source.iterdir() if p.is_dir() and (m := EVALUATOR_DIR.fullmatch(p.name))]
    folders = sorted(matched, key=lambda pm: (pm[1]["kind"] != "H", int(pm[1]["number"])))  # humans first, then agents, each by number

    # Key sheet: one row per transcript with its code under each kind.
    by_transcript = {kind: {t: c for c, t in key.items()} for kind, key in keys.items()}
    key_rows = []
    for t in transcripts:
        m = TRANSCRIPT.fullmatch(t)
        key_rows.append({"transcripcion": t, "participante": m["participant"], "momento": m["moment"],
                         **{f"codigo_{kind}": by_transcript[kind][t] for kind in keys}})
    key_df = pd.DataFrame(key_rows)
    key_df["_m"] = key_df["momento"].map(MOMENTS.index)
    key_df = key_df.sort_values(["participante", "_m"]).drop(columns="_m").reset_index(drop=True)

    # One row per transcript and capacity.
    results = key_df.loc[key_df.index.repeat(len(CAPACITIES))].reset_index(drop=True)
    results.insert(3, "capacidad", list(CAPACITIES) * len(key_df))

    evaluator_rows = []
    for folder, m in folders:
        kind, column = m["kind"], f"{m['kind']}{m['number']}"
        if column in results.columns:
            raise ValueError(f"two folders give the evaluator column {column}")
        print(f"{column:<4} <- {folder.name}")
        ratings, summary = read_evaluator(folder, kind, keys[kind])
        results[column] = [ratings.get((t, c), float("nan")) for t, c in zip(results["transcripcion"], results["capacidad"])]
        results[column] = results[column].astype("Int64")
        evaluator_rows.append({"columna": column, "carpeta": folder.name, "tipo": "LLM agent" if kind == "A" else "human",
                               "clave": KEYS[kind], **summary})
        print(f"      {summary['files_read']} files, {summary['ratings_filled']}/{summary['ratings_expected']} ratings")

    # Expected evaluators without a folder: an empty column, so the layout never changes.
    for column in EXPECTED_EVALUATORS:
        if column not in results.columns:
            kind = column[0]
            print(f"{column:<4} <- (no folder)")
            warn(f"no folder {column}_<label> in {source}; column {column} left empty")
            results[column] = pd.Series([pd.NA] * len(results), dtype="Int64")
            evaluator_rows.append({"columna": column, "carpeta": "(not found)",
                                   "tipo": "LLM agent" if kind == "A" else "human", "clave": KEYS[kind],
                                   "files_read": 0, "codes_without_file": "all", "ratings_filled": 0,
                                   "ratings_expected": len(keys[kind]) * len(CAPACITIES)})

    # Identification columns first, then the expected evaluators, then any others found.
    lead = ["transcripcion", "participante", "momento", "capacidad", *(f"codigo_{k}" for k in keys)]
    extra = [c for c in results.columns if c not in lead and c not in EXPECTED_EVALUATORS]
    results = results[lead + list(EXPECTED_EVALUATORS) + extra]
    order = {c: i for i, c in enumerate([*EXPECTED_EVALUATORS, *extra])}
    evaluator_rows.sort(key=lambda r: order[r["columna"]])
    return results, pd.DataFrame(evaluator_rows), key_df


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for i, col in enumerate(df.columns, start=1):
                width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)])
                ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 6), 60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=SOURCE_DIR, help="folder with keys/ and the evaluator folders")
    parser.add_argument("--out", type=Path, default=OUT_FILE, help="summary workbook to write")
    args = parser.parse_args()

    results, evaluators, key = compile_ratings(args.source)
    sheets = {"results_vertical": results, "evaluators": evaluators, "key": key}
    if warnings:
        sheets["warnings"] = pd.DataFrame({"warning": warnings})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(args.out, sheets)
    print(f"\nWrote {args.out} ({len(results)} rows; {len(warnings)} warnings)")


if __name__ == "__main__":
    main()
