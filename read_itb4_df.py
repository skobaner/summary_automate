# read_itb4_df.py
from pathlib import Path
from typing import List

import pandas as pd
from workbook_utils import (
    extract_itb_number,
    extract_itb_number_from_workbook,
    find_summary_workbook,
)

DATA_DIR = "data"
ITB4_SHEET_FMT = "ITB4-{itb}"


def find_summary_file(data_dir: str = DATA_DIR) -> Path:
    """Backward-compatible wrapper around shared workbook discovery."""
    return find_summary_workbook(data_dir)


def extract_itb_number_from_filename(filename: str) -> str:
    """Backward-compatible wrapper around shared ITB extraction."""
    return extract_itb_number(filename)


def load_itb4_df(
    data_dir: str = DATA_DIR,
    filepath: str | Path | None = None,
    itb: str | int | None = None,
) -> tuple[pd.DataFrame, str, Path]:
    """
    Reads the sheet ITB4-{itb} from the Summary workbook.

    If `filepath` is None, auto-picks the first Excel file in ./data containing "summary".
    If `itb` is None, infers it from the filename.

    Returns:
      df_itb4, itb (string), workbook_path (Path)
    """
    # 1) Choose workbook
    wb_path = Path(filepath) if filepath is not None else find_summary_workbook(data_dir)

    # 2) Determine itb
    if itb is not None:
        itb_str = str(itb)
    else:
        try:
            itb_str = extract_itb_number(wb_path.name)
        except ValueError:
            itb_str = extract_itb_number_from_workbook(wb_path)

    # 3) Sheet name
    sheet_name = ITB4_SHEET_FMT.format(itb=itb_str)

    # 4) Read (header row assumed to be first row of the table)
    df_itb4 = pd.read_excel(
        wb_path,
        sheet_name=sheet_name,
        engine="openpyxl"
    )

    # 5) Clean: drop fully empty rows/cols
    df_itb4 = df_itb4.dropna(how="all").dropna(axis=1, how="all")

    return df_itb4, itb_str, wb_path


def build_itb4_pivot(
    df_itb4: pd.DataFrame,
    itb: str | int,
    selected_codes: List[str],
    itb_col: str = "ITB",
    mx_cbs_col: str = "MX CBS Code 1",
    cbc_description: pd.Series | dict | None = None,   # ✅ now accepts mapping/Series
    vendor_col: str = "Vendor",
    value_col: str = "Total Cost",
    fill_value: float = 0.0,
    drop_all_zero_rows: bool = True,   # ✅ keep
) -> pd.DataFrame:
    """
    Pivot:

      Rows:    MX CBS Code 1 (filtered to selected_codes), Vendor
              BUT DISPLAYED as: "MX CBS Code 1 — DESCRIPTION"
      Columns: ITB (filtered to ITB{itb}A, ITB{itb}F2, ITB{itb}F3, ITB{itb}F4)
      Values:  Sum of Total Cost

    Optional:
      drop_all_zero_rows=True removes pivot rows where all values are zero.

    NOTE:
      Filtering is still performed on the raw MX CBS Code 1 values (selected_codes).
      We only change the displayed row label by concatenating DESCRIPTION.
    """

    required = {itb_col, mx_cbs_col, vendor_col, value_col}
    missing = required - set(df_itb4.columns)
    if missing:
        raise KeyError(f"Missing required columns in ITB4 df: {sorted(missing)}")

    df = df_itb4.copy()

    # -----------------------------
    # Filter MX CBS Code 1 rows (unchanged)
    # -----------------------------
    df[mx_cbs_col] = df[mx_cbs_col].astype(str)
    df = df[df[mx_cbs_col].isin(selected_codes)].copy()

    if df.empty:
        raise ValueError("No rows remain after filtering to selected MX CBS codes.")

    # -----------------------------
    # Filter ITB values (unchanged)
    # -----------------------------
    itb = str(itb)

    allowed_itbs = [
        f"ITB{itb}A",
        f"ITB{itb}F2",
        f"ITB{itb}F3",
        f"ITB{itb}F4",
    ]

    df[itb_col] = df[itb_col].astype(str)
    df = df[df[itb_col].isin(allowed_itbs)].copy()

    if df.empty:
        raise ValueError("No rows remain after filtering ITB values.")

    # -----------------------------
    # Numeric Total Cost (unchanged)
    # -----------------------------
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=[vendor_col, value_col])

    # -----------------------------
    # ✅ NEW: concatenate DESCRIPTION into MX CBS Code 1 for display ONLY
    # -----------------------------
    if cbc_description is not None:
        if isinstance(cbc_description, pd.Series):
            desc_map = cbc_description
        else:
            desc_map = pd.Series(cbc_description)

        # normalize mapping index to string for safe lookup
        desc_map.index = desc_map.index.astype(str)

        codes = df[mx_cbs_col].astype(str).str.strip()
        desc = codes.map(lambda c: str(desc_map.get(c, "")).strip())

        # if desc is empty -> keep code only; else "code — desc"
        df[mx_cbs_col] = codes.where(desc.eq(""), codes + " — " + desc)

    # -----------------------------
    # Pivot Table (unchanged except rows now include concatenated label)
    # -----------------------------
    pivot = pd.pivot_table(
        df,
        index=[mx_cbs_col, vendor_col],
        columns=itb_col,
        values=value_col,
        aggfunc="sum",
        fill_value=fill_value
    )

    pivot.columns.name = None

    # -----------------------------
    # ✅ Drop rows where all values are zero (unchanged)
    # -----------------------------
    if drop_all_zero_rows:
        pivot = pivot.loc[(pivot != 0).any(axis=1)]

    return pivot
