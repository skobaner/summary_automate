# read_summary_df.py
#
# Summary reader + spend-tail selector (FULL FILE)
#
# What this module does:
# 1) Auto-detect the Summary Excel file in ./data (filename contains "summary")
# 2) Infer ITB number from filename
# 3) Read sheet: "Summary-ITB{itb} (AFP BILLING)" with headers on row 4 (header=3)
# 4) Select static worksheet columns by index (your chosen list)
# 5) Compute horizontal analysis:
#       Budget = subset index 2 (Excel col I)
#       Cumulative = subset index 5 (Excel col L)
#       % Spent = cumulative / budget (numeric ratio)
# 6) Remove the cumulative totals row directly below headers
# 7) Select CBC codes in bottom/top percentiles of % Spent (two dicts)
# 8) Provide a convenience wrapper returning bottom/top + selected_codes
# 9) Provide a helper to return the cost-analysis table filtered to selected CBC codes
# 10) NEW: Return CBC->DESCRIPTION mapping for selected CBC codes (as pd.Series)

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from workbook_utils import (
    extract_itb_number,
    extract_itb_number_from_workbook,
    find_summary_workbook,
)


# -----------------------
# Config
# -----------------------
DATA_DIR = "data"
SUMMARY_SHEET_FMT = "Summary-ITB{itb} (AFP BILLING)"

# CBC field name in the Summary subset
CBC_FIELD_SUMMARY = "MX CBS POS CODE"
DESCRIPTION_FIELD = "DESCRIPTION"

# Default percentiles
BOTTOM_PCT = 10.0
TOP_PCT = 10.0

# Static worksheet columns (0-based indices after reading the full sheet)
# Your chosen set: includes I and L needed for budget/cumulative logic
STATIC_COL_IDX = [6, 7, 8, 10, 11, 12, 14, 15, 16, 17, 18]
BUDGET_COL_POS = 2
CUMULATIVE_COL_POS = 5


# -----------------------
# Helpers
# -----------------------
def normalize_header(x) -> str:
    """Normalize whitespace in column headers."""
    return re.sub(r"\s+", " ", str(x)).strip()


def find_summary_file(data_dir: str = DATA_DIR) -> Path:
    """Backward-compatible wrapper around shared workbook discovery."""
    return find_summary_workbook(data_dir)


def extract_itb_number_from_filename(filename: str) -> str:
    """Backward-compatible wrapper around shared ITB extraction."""
    return extract_itb_number(filename)


def build_cbc_description_series(
    df: pd.DataFrame,
    selected_codes: List[str],
    *,
    cbc_col: str = CBC_FIELD_SUMMARY,
    desc_col: str = DESCRIPTION_FIELD,
) -> pd.Series:
    """
    Build a Series mapping CBC code -> DESCRIPTION for the selected codes.
    - Prefers non-empty DESCRIPTION if duplicates exist.
    - Returns a Series indexed by CBC code (strings), values are DESCRIPTION strings (may be "").
    """
    if not selected_codes:
        return pd.Series(dtype="string")

    if cbc_col not in df.columns:
        raise KeyError(f"'{cbc_col}' not found in df.columns")
    if desc_col not in df.columns:
        raise KeyError(f"'{desc_col}' not found in df.columns")

    work = df[[cbc_col, desc_col]].copy()
    work[cbc_col] = work[cbc_col].astype(str).str.strip()
    work[desc_col] = work[desc_col].fillna("").astype(str).str.strip()

    # Restrict to selected codes
    sel = {str(x).strip() for x in selected_codes}
    work = work[work[cbc_col].isin(sel)].copy()

    if work.empty:
        # Return aligned mapping for all selected codes even if missing
        return pd.Series({str(x).strip(): "" for x in selected_codes}, dtype="string")

    # Prefer non-empty descriptions when duplicates exist
    work["_has_desc"] = work[desc_col].ne("")
    work = work.sort_values("_has_desc", ascending=False).drop(columns="_has_desc")
    work = work.drop_duplicates(subset=[cbc_col], keep="first")

    s = work.set_index(cbc_col)[desc_col]

    # Ensure we return ALL selected codes (missing -> "")
    s = s.reindex([str(x).strip() for x in selected_codes]).fillna("").astype("string")
    return s


# -----------------------
# Reading Summary + analysis
# -----------------------
def read_static_columns(summary_filepath: Path, *, itb: str | None = None) -> pd.DataFrame:
    """
    Read Summary-ITB{itb} (AFP BILLING), with headers in row 4 (header=3),
    then select your static worksheet columns by 0-based index.

    Returns a DataFrame with normalized headers.
    """
    if itb is not None:
        itb_value = str(itb)
    else:
        try:
            itb_value = extract_itb_number(summary_filepath.name)
        except ValueError:
            itb_value = extract_itb_number_from_workbook(summary_filepath)
    sheet_name = SUMMARY_SHEET_FMT.format(itb=itb_value)

    df = pd.read_excel(
        summary_filepath,
        sheet_name=sheet_name,
        header=3,  # row 4 has headers
        engine="openpyxl",
    )

    if df.shape[1] <= max(STATIC_COL_IDX):
        raise IndexError(
            f"Sheet '{sheet_name}' has only {df.shape[1]} columns; "
            f"expected at least {max(STATIC_COL_IDX) + 1}."
        )

    out = df.iloc[:, STATIC_COL_IDX].copy()
    out.columns = [normalize_header(c) for c in out.columns]
    return out


def add_budget_vs_cumulative_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute horizontal analysis in the selected subset:
      - Budget = subset index 2 (Excel column I)
      - Cumulative so far = subset index 5 (Excel column L)
      - Variance (Cumulative - Budget)
      - Remaining Budget (Budget - Cumulative)
      - % Spent = cumulative / budget (numeric ratio)

    Returns a new DataFrame with added columns.
    """
    out = df.copy()

    if out.shape[1] <= CUMULATIVE_COL_POS:
        raise IndexError(
            "Expected at least 6 columns in the static subset "
            "(need indices 2 and 5 for Budget/Cumulative)."
        )

    budget_col = out.columns[BUDGET_COL_POS]
    cumulative_col = out.columns[CUMULATIVE_COL_POS]

    budget = pd.to_numeric(out[budget_col], errors="coerce")
    cumulative = pd.to_numeric(out[cumulative_col], errors="coerce")

    out["Variance (Cumulative - Budget)"] = cumulative - budget
    out["Remaining Budget"] = budget - cumulative
    out["% Spent"] = np.where(
        (budget.isna()) | (budget == 0),
        np.nan,
        cumulative / budget,
    )

    return out


def remove_cumulative_row(df: pd.DataFrame) -> pd.DataFrame:
    """
    Removes the cumulative totals row immediately below headers (your rule).
    """
    return df.iloc[1:].reset_index(drop=True)


def load_summary_df(
    data_dir: str = DATA_DIR,
    filepath: str | Path | None = None,
    itb: str | int | None = None,
) -> tuple[pd.DataFrame, str, Path]:
    """
    Load + process the Summary billing table.

    Returns:
      df: processed summary df (static cols + analysis + removed cumulative row)
      itb: ITB number as string (no padding)
      summary_path: Path to the chosen Summary file
    """
    summary_path = Path(filepath) if filepath is not None else find_summary_workbook(data_dir)
    if itb is not None:
        itb_value = str(itb)
    else:
        try:
            itb_value = extract_itb_number(summary_path.name)
        except ValueError:
            itb_value = extract_itb_number_from_workbook(summary_path)

    df = read_static_columns(summary_path, itb=itb_value)
    df = add_budget_vs_cumulative_analysis(df)
    df = remove_cumulative_row(df)

    return df, itb_value, summary_path


# -----------------------
# Spend-tail CBC selection
# -----------------------
def cbc_codes_by_spent_percentiles(
    df: pd.DataFrame,
    spent_col: str = "% Spent",
    cbc_col: str = CBC_FIELD_SUMMARY,
    bottom_pct: float = BOTTOM_PCT,
    top_pct: float = TOP_PCT,
    include_ties: bool = True,
) -> Tuple[Dict, Dict]:
    """
    Return TWO dicts for bottom/top tails of % Spent.

      bottom_result = {"threshold": float, "codes": list[str], "rows": DataFrame}
      top_result    = {"threshold": float, "codes": list[str], "rows": DataFrame}

    Notes:
    - Treats % Spent as numeric ratios (0.42, 1.15), not formatted percent strings.
    - Drops rows missing CBC code or % Spent.
    - include_ties=True includes all rows tied at the threshold cutoff.
    """
    if spent_col not in df.columns:
        raise KeyError(f"'{spent_col}' not found in df.columns")
    if cbc_col not in df.columns:
        raise KeyError(f"'{cbc_col}' not found in df.columns")

    work = df[[cbc_col, spent_col]].copy()
    work[spent_col] = pd.to_numeric(work[spent_col], errors="coerce")
    work = work.dropna(subset=[cbc_col, spent_col])

    if work.empty:
        empty = {"threshold": np.nan, "codes": [], "rows": work}
        return empty, empty

    bottom_thr = float(work[spent_col].quantile(bottom_pct / 100.0))
    top_thr = float(work[spent_col].quantile(1.0 - top_pct / 100.0))

    if include_ties:
        bottom_rows = work[work[spent_col] <= bottom_thr].copy()
        top_rows = work[work[spent_col] >= top_thr].copy()
    else:
        bottom_rows = work[work[spent_col] < bottom_thr].copy()
        top_rows = work[work[spent_col] > top_thr].copy()

    def unique_preserve_order(series: pd.Series) -> List[str]:
        seen = set()
        out_list: List[str] = []
        for v in series.astype(str).tolist():
            if v not in seen:
                seen.add(v)
                out_list.append(v)
        return out_list

    bottom_result = {
        "threshold": bottom_thr,
        "codes": unique_preserve_order(bottom_rows[cbc_col]),
        "rows": bottom_rows.reset_index(drop=True),
    }
    top_result = {
        "threshold": top_thr,
        "codes": unique_preserve_order(top_rows[cbc_col]),
        "rows": top_rows.reset_index(drop=True),
    }
    return bottom_result, top_result


def select_spend_tail_cbc_codes(
    df: pd.DataFrame,
    bottom_pct: float = BOTTOM_PCT,
    top_pct: float = TOP_PCT,
    include_ties: bool = True,
    spent_col: str = "% Spent",
    cbc_col: str = CBC_FIELD_SUMMARY,
) -> Dict:
    """
    Convenience wrapper returning a single dict:
      {
        "bottom": <bottom_result>,
        "top": <top_result>,
        "selected_codes": bottom.codes + top.codes,
        "cbc_description": Series indexed by CBC code with DESCRIPTION values
      }
    """
    bottom, top = cbc_codes_by_spent_percentiles(
        df=df,
        spent_col=spent_col,
        cbc_col=cbc_col,
        bottom_pct=bottom_pct,
        top_pct=top_pct,
        include_ties=include_ties,
    )

    selected_codes = bottom["codes"] + top["codes"]

    cbc_description = build_cbc_description_series(
        df=df,
        selected_codes=selected_codes,
        cbc_col=cbc_col,
        desc_col=DESCRIPTION_FIELD,
    )

    return {
        "bottom": bottom,
        "top": top,
        "selected_codes": selected_codes,
        "cbc_description": cbc_description,
    }


# -----------------------
# Cost analysis table for selected codes
# -----------------------
def get_cost_analysis_for_codes(
    df: pd.DataFrame,
    selected_codes: List[str],
    cbc_col: str = CBC_FIELD_SUMMARY,
    sort_by: str = "% Spent",
    sort_desc: bool = True,
) -> pd.DataFrame:
    """
    Return the cost-analysis table filtered to `selected_codes`,
    but only with the key requested columns:

    - MX CBS POS CODE
    - DESCRIPTION
    - Current Budget Q4 (without fee)
    - Budget column (subset index 2)
    - Cumulative column (subset index 5)
    - % Spent
    - Variance + Remaining Budget
    """
    if cbc_col not in df.columns:
        raise KeyError(f"'{cbc_col}' not found in df.columns")

    if not selected_codes:
        return df.head(0).copy()

    work = df.copy()
    work[cbc_col] = work[cbc_col].astype(str)

    sel = {str(x) for x in selected_codes}
    out = work[work[cbc_col].isin(sel)].copy()

    # Budget + cumulative columns (by position in processed summary)
    budget_col = out.columns[BUDGET_COL_POS]
    cumulative_col = out.columns[CUMULATIVE_COL_POS]

    # Keep only requested + spend-related columns
    keep_cols = [
        "MX CBS POS CODE",
        DESCRIPTION_FIELD,
        "Current Budget Q4 (without fee)",
        budget_col,
        cumulative_col,
        "Variance (Cumulative - Budget)",
        "Remaining Budget",
        "% Spent",
    ]

    # Only keep cols that actually exist (safe)
    keep_cols = [c for c in keep_cols if c in out.columns]

    out = out[keep_cols]

    # Sort by % Spent if present
    if sort_by in out.columns:
        out[sort_by] = pd.to_numeric(out[sort_by], errors="coerce")
        out = out.sort_values(sort_by, ascending=not sort_desc)

    return out.reset_index(drop=True)
