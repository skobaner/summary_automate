# render_cost_analysis_html.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Iterable
import html

import pandas as pd


def _make_unique_columns(cols: Iterable) -> list[str]:
    """
    Ensure column names are unique.
    If duplicates exist, suffix with __2, __3, ...
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in cols:
        base = str(c)
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}__{n}")
    return out


def _fmt_money(x) -> str:
    if pd.isna(x):
        return ""
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)


def _fmt_ratio(x) -> str:
    # % Spent is a ratio (0.25, 1.10). Show as percent with 1 decimal.
    if pd.isna(x):
        return ""
    try:
        return f"{float(x) * 100:,.1f}%"
    except Exception:
        return str(x)


def _fmt_number(x) -> str:
    if pd.isna(x):
        return ""
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)


def render_cost_analysis_html(
    df: pd.DataFrame,
    output_path: str | Path,
    *,
    title: str = "Cost Analysis",
    subtitle: Optional[str] = None,
) -> Path:
    """
    Render a clean HTML report for the cost analysis DataFrame without df.style/jinja2.
    Handles duplicate column names safely.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out = df.copy()

    # IMPORTANT: make columns unique to avoid Series-vs-DataFrame ambiguity
    out.columns = _make_unique_columns(out.columns)

    # Decide which columns to format
    # (Update these if your column names differ)
    ratio_cols = [c for c in out.columns if c.strip() == "% Spent"]
    money_like = {
        "Current Budget Q4 (without fee)",
        "Variance (Cumulative - Budget)",
        "Remaining Budget",
    }

    # Also include the "Budget" and "Cumulative" columns you selected by index.
    # Since those names come from Excel, we detect them by position if present:
    # We expect in your cost_analysis_df you kept: [cbc, desc, current budget, budget_col, cumulative_col, variance, remaining, % spent]
    # We'll treat columns 3 and 4 as money if they exist.
    idx_money_cols = []
    if out.shape[1] >= 5:
        idx_money_cols = [out.columns[3], out.columns[4]]

    money_cols = [c for c in out.columns if c in money_like] + idx_money_cols

    # Build HTML table
    def th(text: str) -> str:
        return f"<th>{html.escape(text)}</th>"

    def td(text: str) -> str:
        return f"<td>{html.escape(text)}</td>"

    headers_html = "<tr>" + "".join(th(c) for c in out.columns) + "</tr>"

    body_rows = []
    for _, row in out.iterrows():
        tds = []
        for c in out.columns:
            v = row[c]

            # numeric formatting rules
            if c in ratio_cols:
                cell = _fmt_ratio(pd.to_numeric(v, errors="coerce"))
            elif c in money_cols:
                cell = _fmt_money(pd.to_numeric(v, errors="coerce"))
            else:
                # leave text columns alone, but format generic numbers nicely
                num = pd.to_numeric(v, errors="coerce")
                if pd.notna(num) and str(v).strip() != "":
                    cell = _fmt_money(num)  # default money-ish formatting looks best here
                else:
                    cell = "" if pd.isna(v) else str(v)

            tds.append(td(cell))
        body_rows.append("<tr>" + "".join(tds) + "</tr>")

    subtitle_html = ""
    if subtitle:
        subtitle_html = f"<div class='subtitle'>{html.escape(subtitle)}</div>"

    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  body {{
    margin: 0;
    background: #0b0b0b;
    font-family: Arial, Helvetica, sans-serif;
    color: #111;
  }}
  .page {{
    width: 1200px;
    margin: 32px auto;
    background: #fff;
    padding: 28px 32px;
    box-sizing: border-box;
  }}
  h1 {{
    margin: 0 0 6px 0;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.2px;
  }}
  .subtitle {{
    margin: 0 0 16px 0;
    font-size: 12px;
    color: #444;
  }}
  .table-wrap {{
    overflow: auto;
    border: 1px solid #ddd;
    border-radius: 8px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  th, td {{
    border-bottom: 1px solid #eee;
    padding: 8px 10px;
    vertical-align: top;
    white-space: nowrap;
  }}
  th {{
    background: #f6f7f8;
    text-align: left;
    font-weight: 700;
  }}
  tr:hover td {{
    background: #fafafa;
  }}
  .note {{
    margin-top: 10px;
    font-size: 11px;
    color: #666;
  }}
</style>
</head>
<body>
  <div class="page">
    <h1>{html.escape(title)}</h1>
    {subtitle_html}
    <div class="table-wrap">
      <table>
        <thead>{headers_html}</thead>
        <tbody>
          {"".join(body_rows)}
        </tbody>
      </table>
    </div>
    <div class="note">Amounts shown as plain numbers (no currency symbol). % Spent shown as percent.</div>
  </div>
</body>
</html>
"""

    output_path.write_text(html_text, encoding="utf-8")
    return output_path
