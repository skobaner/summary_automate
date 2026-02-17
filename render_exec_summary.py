from pathlib import Path
import html


def fmt_m(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    m = value / 1_000_000
    if decimals == 0:
        return f"${m:,.0f}M"
    return f"${m:,.{decimals}f}M"


def fmt_variance_m(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    m = value / 1_000_000
    sign = "+" if m >= 0 else "−"
    return f"{sign}${abs(m):,.{decimals}f}M"


def generate_exec_summary(metrics: dict, output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    itb = metrics.get("itb", "")
    itb_int = int(itb) if str(itb).isdigit() else None

    nw_track_budget_m = metrics.get("nw_track_budget_m")
    actual_cost_to_date_m = metrics.get("actual_cost_to_date_m")
    itb_cost_applied_m = metrics.get("itb_cost_applied_m")
    itb_cost_applied_breakdown = metrics.get("itb_cost_applied_breakdown", {})
    total_cost_submitted_to_date_m = metrics.get("total_cost_submitted_to_date_m")

    variance_itb_vs_prev_m = metrics.get("variance_itb_vs_prev_m")
    variance_reason = metrics.get("variance_itb_vs_prev_reason") or ""
    total_proposed_deauth_m = metrics.get("total_proposed_deauth_m")

    # -----------------------------
    # Month bullets (UPDATED: add Actual/Accrual/Forecast tags)
    #   1st item  -> Actual
    #   2nd item  -> Accrual
    #   remaining -> Forecast
    # -----------------------------
    month_items = []
    for i, (label, val) in enumerate(itb_cost_applied_breakdown.items()):
        if i == 0:
            tag = "Actual"
        elif i == 1:
            tag = "Accrual"
        else:
            tag = "Forecast"

        month_items.append(
            f"<li>{html.escape(str(label))} <span class='amt'>{fmt_m(val, 0)}</span> - {tag}</li>"
        )
    month_list_html = "\n".join(month_items)

    variance_reason_html = f" due to {html.escape(variance_reason)}" if variance_reason else ""

    out_path = output_dir / f"executive_summary_ITB{itb}.html"

  
    asof_itb_label = f"ITB{itb_int - 1:03d}" if itb_int is not None and itb_int > 0 else f"ITB{itb}"
    itb_cost_applied_label = f"ITB{itb_int:03d}" if itb_int is not None else f"ITB{itb}"

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Executive Summary - ITB{html.escape(str(itb))}</title>
  <style>
    :root {{ --text:#111; --muted:#666; --rule:#222; --bg:#fff; }}
    body {{ margin:0; background:#0b0b0b; font-family: Arial, Helvetica, sans-serif; color:var(--text); }}
    .page {{
      width: 960px; height: 540px; margin: 32px auto; background: var(--bg);
      box-sizing: border-box; padding: 36px 48px 40px 48px; position: relative;
    }}
    h1 {{ margin:0 0 18px 0; font-size:22px; letter-spacing:0.3px; font-weight:700; }}
    ul {{ margin:0; padding-left:22px; font-size:16px; line-height:1.55; }}
    li {{ margin:6px 0; }}
    .amt {{ font-weight:700; }}
    .sub {{ margin-top:8px; padding-left:22px; list-style-type:disc; font-size:15px; }}
    .sub li {{ margin:5px 0; }}
    .footer {{
      position:absolute; left:48px; right:48px; bottom:16px;
      display:flex; align-items:center; justify-content:space-between;
      font-size:11px; color:var(--muted);
    }}
    .rule {{ position:absolute; left:48px; right:48px; bottom:36px; height:1px; background:var(--rule); }}
    .brand {{ font-weight:700; color:#111; font-size:12px; }}
    .right {{ display:flex; gap:18px; align-items:center; }}
    .pageNo {{ color:#111; font-weight:700; }}
  </style>
</head>
<body>
  <div class="page">
    <h1>EXECUTIVE SUMMARY</h1>

    <ul>
      <li>NW Track Budget <span class="amt">{fmt_m(nw_track_budget_m, 0)}</span> (CJV ITB Q4 Update, excluding MX additional cost and contingency)</li>
      <li>Actual Cost to Date <span class="amt">{fmt_m(actual_cost_to_date_m, 0)}</span> (as of {asof_itb_label})</li>

      <li>
        {itb_cost_applied_label} Cost Applied <span class="amt">{fmt_m(itb_cost_applied_m, 0)}</span>:
        <ul class="sub">
          {month_list_html}
        </ul>
      </li>

      <li>Total Cost Submitted to Date <span class="amt">{fmt_m(total_cost_submitted_to_date_m, 0)}</span></li>
      <li>Total Proposed Deauthorization of <span class="amt">{fmt_m(total_proposed_deauth_m, 0)}</span> on ITB{itb} Cost Applied</li>
    </ul>

    <div class="rule"></div>
    <div class="footer">
      <div class="brand">METROLINX</div>
      <div class="right">
        <div>{html.escape("Note: All figures include Fee")}</div>
        <div class="pageNo">NW TRACK&nbsp;&nbsp;|&nbsp;&nbsp;4</div>
      </div>
    </div>
  </div>
</body>
</html>
"""
    out_path.write_text(html_text, encoding="utf-8")
    return out_path
