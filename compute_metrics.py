import pandas as pd


CBC_FIELD_SUMMARY = "MX CBS POS CODE"


def to_float(v):
    v = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(v) else float(v)


def compute_cost_metrics(df: pd.DataFrame, itb: str) -> dict:
    """
    Computes and returns the metrics dictionary from df + itb.
    Assumes:
      - df has column 'Current Budget Q4 (without fee)'
      - df has column 'MX CBS POS CODE'
      - df has ITB columns like ITB13/ITB14/ITB15 ...
      - month columns are df.columns[6:10]
    """
    # --- NW Track Budget: sum of Current Budget where code startswith MX.2 ---
    nw_track_budget_m = (
        df.loc[
            df[CBC_FIELD_SUMMARY].astype(str).str.startswith("MX.2", na=False),
            "Current Budget Q4 (without fee)"
        ]
        .pipe(pd.to_numeric, errors="coerce")
        .sum()
    )
    nw_track_budget_m = float(nw_track_budget_m)

    # --- Actual Cost to Date: ITB{itb} at row where code == MX.2 ---
    itb_col = f"ITB{itb}"
    mx2_mask = df[CBC_FIELD_SUMMARY].astype(str).eq("MX.2")
    mx2 = df.loc[mx2_mask]

    if mx2.empty:
        raise ValueError("No row found where MX CBS POS CODE == 'MX.2'")
    if len(mx2) > 1:
        raise ValueError("Multiple rows found where MX CBS POS CODE == 'MX.2'")

    mx2_row = mx2.iloc[0]
    actual_cost_to_date_m = to_float(mx2_row[itb_col])

    # --- Month labels/values from columns 7-10 (indices 6..9) at MX.2 row ---
    month_cols = list(df.columns[6:10])
    if len(month_cols) != 4:
        raise ValueError(f"Expected 4 month columns from df.columns[6:10], got {len(month_cols)}")

    month_labels = [pd.to_datetime(c).strftime("%b-%y") for c in month_cols]
    month_vals = [to_float(mx2_row[c]) for c in month_cols]

    itb_cost_applied_breakdown = dict(zip(month_labels, month_vals))

    itb_cost_applied_m = float(sum(v for v in itb_cost_applied_breakdown.values() if v is not None))

    total_cost_submitted_to_date_m = None
    if actual_cost_to_date_m is not None:
        total_cost_submitted_to_date_m = float(actual_cost_to_date_m + itb_cost_applied_m)

    # placeholders until you define the rules
    variance_itb_vs_prev_m = None
    total_proposed_deauth_m = None
    variance_itb_vs_prev_reason = None

    return {
        "itb": str(itb),

        "nw_track_budget_m": nw_track_budget_m,
        "actual_cost_to_date_m": actual_cost_to_date_m,

        "itb_cost_applied_m": itb_cost_applied_m,
        "itb_cost_applied_breakdown": itb_cost_applied_breakdown,

        "total_cost_submitted_to_date_m": total_cost_submitted_to_date_m,

        "variance_itb_vs_prev_m": variance_itb_vs_prev_m,
        "variance_itb_vs_prev_reason": variance_itb_vs_prev_reason,
        "total_proposed_deauth_m": total_proposed_deauth_m,
    }
