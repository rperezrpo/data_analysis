"""Inter-rater reliability of the capacity ratings compiled by 01_compile_ratings.py.

Input: data/processed/ratings_summary.xlsx, sheet 'results_vertical' - one row per interview
and capacity (a "unit"), one column per evaluator (H1 ... humans, A1 ...
LLM agents), levels on the rubric's ordinal 1-5 scale; blank = not rated.

Three indicators, for each group of evaluators (GROUPS) and each scope (all
capacities pooled, then each capacity on its own):

(i)  Raw agreement. For every unit with at least two ratings, the share of
     rater pairs that gave exactly the same level,
         p_u = sum_k r_uk (r_uk - 1) / (r_u (r_u - 1)),
     where r_uk is the number of raters who gave level k to unit u and r_u
     the number who rated it. Reported as the mean of p_u over units and its
     standard deviation across units (sample SD, ddof = 1). The mean is irrCAC's
     percent agreement (CAC(..., weights="identity").gwet()["est"]["pa"]); the SD
     is computed here, since irrCAC does not return the per-unit p_u. The script
     stops if the mean of p_u differs from irrCAC's pa.

(ii) Krippendorff's alpha with the ordinal difference function
     (Krippendorff, 2019, ch. 12), from the krippendorff package
     (krippendorff.alpha, level_of_measurement="ordinal"). Units with fewer than
     two ratings are not pairable and drop out. irrCAC's krippendorff() with
     "ordinal" weights is NOT this coefficient: it uses Gwet's fixed ordinal
     weights instead of Krippendorff's ordinal metric, which depends on the
     observed marginals. As a guard on the input, the nominal and interval
     alphas of the two libraries must agree (they compute the same thing there).

(iii) Gwet's AC2 (Gwet, 2014, ch. 3 and 5) from irrCAC (CAC(...).gwet()), with
     ordinal weights w_kl = 1 - C(|k - l| + 1, 2) / C(q, 2), q = 5 levels, for any
     number of raters and missing ratings. The chance term uses the full
     five-level scale (categories=LEVELS), not only the levels observed. Set
     AC2_WEIGHTS to "quadratic" or "linear" for those weights.

Libraries: irrCAC (Python port of Gwet's R irrCAC; installed with
`pip install --no-deps irrCAC` because 0.4.4 pins scipy==1.12.0, which has no
Python 3.13 build) and krippendorff (Castro). Both versions go into 'settings'.

Output: results/tables/reliability_results.xlsx (sheets 'reliability' and
'settings') and the same table printed to the console.

Usage (from data_analysis/; paths do not depend on the working directory):
    python code/02_reliability_analysis.py
    python code/02_reliability_analysis.py --summary other_summary.xlsx --out other_results.xlsx

References
    Gwet, K. L. (2014). Handbook of inter-rater reliability (4th ed.). Advanced Analytics.
    Krippendorff, K. (2019). Content analysis: An introduction to its methodology (4th ed.). SAGE.
"""
import argparse
import importlib.metadata
import re
from pathlib import Path

import krippendorff
import numpy as np
import pandas as pd
from irrCAC.raw import CAC
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent  # data_analysis/
SUMMARY_FILE = ROOT / "data" / "processed" / "ratings_summary.xlsx"
OUT_FILE = ROOT / "results" / "tables" / "reliability_results.xlsx"
SHEET = "results_vertical"

LEVELS = (1, 2, 3, 4, 5)  # the rubric's ordinal scale
AC2_WEIGHTS = "ordinal"  # "ordinal", "quadratic", "linear" or "identity" (= Gwet's AC1)
ALL_CAPACITIES = "all capacities"

# Group name -> regular expression matched against the evaluator columns.
GROUPS = {
    "Humans": r"H\d+",
    "LLM agents": r"A\d+",
    "All evaluators": r"[AH]\d+",
}
EVALUATOR_COLUMN = re.compile(r"[AH]\d+")
INDICATORS = ("agreement", "agreement_sd", "krippendorff_alpha_ordinal", f"gwet_ac2_{AC2_WEIGHTS}")
DIGITS = 10        # irrCAC rounds its output to this many digits (default 5)
TOLERANCE = 1e-6   # for the cross-checks between libraries


# --- counts --------------------------------------------------------------------

def count_matrix(ratings: np.ndarray) -> np.ndarray:
    """Units x raters (NaN = missing) -> units x levels: r_uk, how many raters gave level k to unit u."""
    return np.stack([(ratings == level).sum(axis=1) for level in LEVELS], axis=1).astype(float)


def check_levels(ratings: np.ndarray) -> None:
    present = ratings[~np.isnan(ratings)]
    outside = sorted(set(present) - set(LEVELS))
    if outside:
        raise ValueError(f"ratings outside the scale {LEVELS}: {outside}")


# --- (i) raw agreement ------------------------------------------------------------

def cac(ratings: np.ndarray, weights: str) -> CAC:
    """irrCAC object for units x raters ratings, on the full five-level scale."""
    return CAC(pd.DataFrame(ratings), weights=weights, categories=list(LEVELS), digits=DIGITS)


def raw_agreement(ratings: np.ndarray, counts: np.ndarray) -> tuple[float, float]:
    """Mean (irrCAC) and SD across units of the share of agreeing rater pairs, over units with >= 2 ratings."""
    r_u = counts.sum(axis=1)
    pairable = r_u >= 2
    if not pairable.any():
        return np.nan, np.nan
    pa = cac(ratings, "identity").gwet()["est"]["pa"]
    # Per-unit shares, only for the SD; their mean must reproduce irrCAC's pa.
    c, r = counts[pairable], r_u[pairable]
    p_u = (c * (c - 1)).sum(axis=1) / (r * (r - 1))
    if abs(p_u.mean() - pa) > TOLERANCE:
        raise RuntimeError(f"mean per-unit agreement {p_u.mean()} differs from irrCAC pa {pa}")
    sd = p_u.std(ddof=1) if len(p_u) > 1 else np.nan
    return float(pa), float(sd)


# --- (ii) Krippendorff's alpha ----------------------------------------------------

def krippendorff_alpha_ordinal(ratings: np.ndarray) -> float:
    data = ratings.T  # the krippendorff package expects raters x units
    try:
        alpha = krippendorff.alpha(reliability_data=data, level_of_measurement="ordinal", value_domain=list(LEVELS))
    except ValueError:
        return np.nan  # e.g. every pairable value in one level: alpha is undefined
    # Guard on the input: irrCAC and krippendorff must agree where they compute the same coefficient.
    for weights, level in (("identity", "nominal"), ("quadratic", "interval")):
        a_irrcac = cac(ratings, weights).krippendorff()["est"]["coefficient_value"]
        a_kripp = krippendorff.alpha(reliability_data=data, level_of_measurement=level, value_domain=list(LEVELS))
        if abs(a_irrcac - a_kripp) > TOLERANCE:
            raise RuntimeError(f"{level} alpha: irrCAC {a_irrcac} vs krippendorff {a_kripp}")
    return float(alpha)


# --- (iii) Gwet's AC2 -----------------------------------------------------------------

def gwet_ac2(ratings: np.ndarray) -> float:
    return float(cac(ratings, AC2_WEIGHTS).gwet()["est"]["coefficient_value"])


# --- analysis -------------------------------------------------------------------------

def reliability_row(ratings: np.ndarray) -> dict:
    counts = count_matrix(ratings)
    r_u = counts.sum(axis=1)
    agreement, agreement_sd = raw_agreement(ratings, counts)
    pairable = bool((r_u >= 2).any())
    return {
        "n_units": int((r_u >= 2).sum()),
        "n_ratings": int(r_u[r_u >= 2].sum()),
        "agreement": agreement,
        "agreement_sd": agreement_sd,
        "krippendorff_alpha_ordinal": krippendorff_alpha_ordinal(ratings) if pairable else np.nan,
        f"gwet_ac2_{AC2_WEIGHTS}": gwet_ac2(ratings) if pairable else np.nan,
    }


def analyse(df: pd.DataFrame) -> pd.DataFrame:
    evaluators = [c for c in df.columns if EVALUATOR_COLUMN.fullmatch(str(c))]
    df[evaluators] = df[evaluators].apply(pd.to_numeric, errors="raise")
    check_levels(df[evaluators].to_numpy(dtype=float))
    capacities = list(dict.fromkeys(df["capacidad"]))  # order of first appearance

    rows = []
    for group, pattern in GROUPS.items():
        columns = [c for c in evaluators if re.fullmatch(pattern, str(c))]
        for scope in [ALL_CAPACITIES, *capacities]:
            subset = df if scope == ALL_CAPACITIES else df[df["capacidad"] == scope]
            # Only evaluators who rated something in this scope count as raters.
            active = [c for c in columns if subset[c].notna().any()]
            row = {"group": group, "scope": scope, "raters": ", ".join(active), "n_raters": len(active)}
            if len(active) < 2:
                # Not enough evaluators with ratings yet: the row is kept, the indicators left blank.
                row.update(dict.fromkeys(INDICATORS, np.nan), n_units=0, n_ratings=0,
                           note="fewer than two evaluators with ratings")
            else:
                row.update(reliability_row(subset[active].to_numpy(dtype=float)))
                row["note"] = "" if row["n_units"] else "no unit rated by two evaluators"
            rows.append(row)
    columns = ["group", "scope", "raters", "n_raters", "n_units", "n_ratings", *INDICATORS, "note"]
    return pd.DataFrame(rows)[columns]


def settings_table() -> pd.DataFrame:
    return pd.DataFrame([
        ("scale", f"ordinal, levels {LEVELS[0]}-{LEVELS[-1]}"),
        ("unit", "one interview x one capacity; 'all capacities' pools the seven capacities"),
        ("raters", "evaluators of the group who rated at least one unit in the scope; "
                   "evaluators missing from the summary or without ratings are left out"),
        ("n_units", "units with at least two ratings (pairable units)"),
        ("n_ratings", "ratings in the pairable units"),
        ("agreement", "mean over pairable units of the share of rater pairs with the same level "
                      "(irrCAC gwet() pa, identity weights)"),
        ("agreement_sd", "standard deviation of that share across pairable units (ddof = 1), computed in the script"),
        ("krippendorff_alpha_ordinal", "Krippendorff's alpha, ordinal difference function "
                                       "(krippendorff.alpha, level_of_measurement='ordinal')"),
        (f"gwet_ac2_{AC2_WEIGHTS}", f"Gwet's AC2, {AC2_WEIGHTS} weights, chance term over all {len(LEVELS)} levels "
                                    f"(irrCAC gwet())"),
        ("check", f"nominal and interval alpha agree between irrCAC and krippendorff (tolerance {TOLERANCE})"),
        *((f"group: {g}", f"evaluator columns matching {p}") for g, p in GROUPS.items()),
        *((f"library: {lib}", importlib.metadata.version(lib)) for lib in ("irrCAC", "krippendorff")),
    ], columns=["item", "definition"])


def write_workbook(path: Path, results: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in {"reliability": results, "settings": settings_table()}.items():
            df.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for i, col in enumerate(df.columns, start=1):
                letter = get_column_letter(i)
                width = max([len(str(col))] + [len(str(v)) for v in df[col]])
                ws.column_dimensions[letter].width = min(max(width + 2, 8), 70)
                if pd.api.types.is_float_dtype(df[col]):
                    for cell in ws[letter][1:]:
                        cell.number_format = "0.000"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--summary", type=Path, default=SUMMARY_FILE, help="workbook written by compile_ratings.py")
    parser.add_argument("--out", type=Path, default=OUT_FILE, help="workbook to write the results to")
    args = parser.parse_args()

    df = pd.read_excel(args.summary, sheet_name=SHEET, dtype={"participante": str})
    results = analyse(df)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(args.out, results)

    with pd.option_context("display.width", 200, "display.max_columns", None, "display.max_rows", None):
        print(results.drop(columns="raters").to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
