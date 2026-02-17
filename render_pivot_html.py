from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


def _fmt_money(x) -> str:
    if pd.isna(x):
        return ""
    try:
        return f"${float(x):,.0f}"
    except Exception:
        return str(x)


def write_pivot_html(
    pivot_df: pd.DataFrame,
    output_path: str | Path,
    title: str = "ITB4 Pivot Summary",
    subtitle: Optional[str] = None,
    show_index: bool = True,
) -> Path:
    """
    Writes a styled HTML report for a pivot table DataFrame.

    Fix: Render MultiIndex row headers sparsely (rowspan-like) so the outer level
    (CBC — DESCRIPTION) appears once for multiple vendor rows, mimicking merged cells.

    Also keeps your existing behavior of collapsing CBC + DESCRIPTION levels into a single
    "CBC — DESCRIPTION" level if the pivot index contains both as separate levels.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pivot_df.copy()

    # If user requests hiding index, convert index to a column (keeps HTML clean)
    if not show_index:
        df = df.reset_index()

    # Currency formatting for numeric columns
    fmt = {}
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            fmt[c] = _fmt_money

    # ---- Collapse MultiIndex (CBC + DESCRIPTION) into a single label if present ----
    if show_index and isinstance(df.index, pd.MultiIndex):
        level_names = [str(x) if x is not None else "" for x in df.index.names]

        cbc_candidates = {
            "MX CBS POS CODE",
            "MX CBS CODE 1",
            "MX CBS Code 1",
            "CBC",
            "CBC Code",
            "CBC CODE",
        }
        desc_candidates = {"DESCRIPTION", "Description", "DESC", "Desc"}

        cbc_level = None
        desc_level = None

        for i, nm in enumerate(level_names):
            if nm in cbc_candidates and cbc_level is None:
                cbc_level = i
            if nm in desc_candidates and desc_level is None:
                desc_level = i

        # If names weren't set, try positional fallback: first two levels
        if cbc_level is None and desc_level is None and df.index.nlevels >= 2:
            cbc_level, desc_level = 0, 1

        if cbc_level is not None and desc_level is not None and cbc_level != desc_level:
            tuples = df.index.tolist()
            combined = []
            for t in tuples:
                cbc = "" if t[cbc_level] is None else str(t[cbc_level]).strip()
                desc = "" if t[desc_level] is None else str(t[desc_level]).strip()
                combined.append(f"{cbc} — {desc}" if desc else cbc)

            keep_levels = [
                i for i in range(df.index.nlevels) if i not in {cbc_level, desc_level}
            ]

            if keep_levels:
                new_tuples = []
                for idx, t in enumerate(tuples):
                    rest = tuple(t[i] for i in keep_levels)
                    new_tuples.append((combined[idx],) + rest)

                new_names = ["CBC — DESCRIPTION"] + [level_names[i] for i in keep_levels]
                df.index = pd.MultiIndex.from_tuples(new_tuples, names=new_names)
            else:
                df.index = pd.Index(combined, name="CBC — DESCRIPTION")
    # -------------------------------------------------------------------------------

    # ✅ FIX: sparse MultiIndex rendering (this gives the "merged cell" look)
    # For MultiIndex rows, pandas Styler can render repeated outer labels as blanks,
    # and uses rowspan in some versions. This is controlled by sparse_index.
    sparse_index = bool(show_index and isinstance(df.index, pd.MultiIndex))

    styled = df.style

    if fmt:
        styled = styled.format(fmt)

    styled = (
        styled.set_table_attributes('class="pivot-table"')
        .set_properties(**{"white-space": "nowrap"})
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("position", "sticky"),
                        ("top", "0"),
                        ("background", "#f5f5f5"),
                        ("z-index", "2"),
                        ("border-bottom", "1px solid #ddd"),
                        ("padding", "10px"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [("border-bottom", "1px solid #eee"), ("padding", "8px 10px")],
                },
                {
                    "selector": "table",
                    "props": [("border-collapse", "collapse"), ("width", "100%")],
                },
                {"selector": "tbody tr:nth-child(even)", "props": [("background", "#fafafa")]},
            ]
        )
    )

    # ✅ IMPORTANT: tell Styler to render sparse index (prevents repeating the CBC label)
    html_table = styled.to_html(sparse_index=sparse_index, sparse_columns=True)

    subtitle_html = f"<div class='subtitle'>{subtitle}</div>" if subtitle else ""

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: #0b0b0b;
      color: #111;
    }}
    .page {{
      max-width: 1200px;
      margin: 28px auto;
      background: #fff;
      padding: 24px 28px 30px 28px;
      border-radius: 10px;
      box-sizing: border-box;
    }}
    .header {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    h1 {{
      font-size: 18px;
      margin: 0;
      letter-spacing: 0.2px;
    }}
    .subtitle {{
      font-size: 12px;
      color: #666;
      margin-top: 4px;
      margin-bottom: 10px;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid #eee;
      border-radius: 8px;
    }}
    .pivot-table {{
      width: 100%;
      font-size: 12px;
    }}
    .pivot-table th {{
      text-align: left;
      font-weight: 700;
    }}
    .pivot-table td {{
      text-align: right;
    }}
    /* MultiIndex row headers show up as <th> inside tbody; align them left */
    .pivot-table tbody th {{
      text-align: left;
      font-weight: 600;
      background: #fff;
      position: sticky;
      left: 0;
      z-index: 1;
      border-right: 1px solid #eee;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <div>
        <h1>{title}</h1>
        {subtitle_html}
      </div>
    </div>

    <div class="table-wrap">
      {html_table}
    </div>
  </div>
</body>
</html>
"""

    output_path.write_text(html_doc, encoding="utf-8")
    return output_path
