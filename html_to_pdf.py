# html_to_pdf.py
# Combine exactly 3 HTML files (exec summary, pivot, cost analysis) into ONE PDF.
# Uses Playwright + merged CSS + print overrides so tables paginate (no scrolling/clipping).
#
# Expected output filenames in ./output (default names, configurable):
#   - 01_exec_summary.html
#   - 02_cost_analysis.html
#   - 03_pivot.html
#
# If your files are named differently, pass them explicitly via `html_files=[...]`.

from __future__ import annotations

from pathlib import Path
import re
from typing import Sequence


_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)
_LINK_CSS_RE = re.compile(
    r"""<link[^>]+rel=["']stylesheet["'][^>]*href=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE | re.DOTALL,
)


def export_combined_report_pdf(
    output_dir: str | Path = "output",
    combined_pdf_name: str = "combined_report.pdf",
    *,
    # Default: three fixed HTML files (recommended, in report order)
    html_files: Sequence[str] = (
        "01_exec_summary.html",
        "02_cost_analysis.html",
        "03_pivot.html",
    ),
    # PDF options
    pdf_format: str = "A4",
    print_background: bool = True,
) -> Path:
    """
    Combine EXACTLY the 3 HTML files into ONE PDF, in the provided order.
    Preserves CSS by inlining <style> blocks AND local <link rel="stylesheet"> files.
    Applies print overrides so:
      - fixed-size ".page" layouts expand naturally for print
      - scroll containers (e.g., .table-wrap) become paginated tables
      - sticky headers don't break layout

    Returns the PDF path.
    """
    output_dir = Path(output_dir).resolve()

    # Resolve the 3 expected HTML paths
    html_paths = [output_dir / name for name in html_files]
    missing = [p.name for p in html_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing HTML file(s) in {output_dir}: {missing}\n"
            f"Expected: {list(html_files)}"
        )

    all_styles: list[str] = []
    sections: list[str] = []

    def try_inline_css_link(html_path: Path, href: str) -> str | None:
        href = href.strip()
        if href.lower().startswith(("http://", "https://", "data:")):
            return None
        css_path = (html_path.parent / href).resolve()
        if css_path.exists() and css_path.is_file():
            try:
                return css_path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    for html_path in html_paths:
        content = html_path.read_text(encoding="utf-8")

        # collect inline <style> blocks
        for s in _STYLE_RE.findall(content):
            all_styles.append(s)

        # collect local linked css stylesheets
        for href in _LINK_CSS_RE.findall(content):
            css_text = try_inline_css_link(html_path, href)
            if css_text:
                all_styles.append(css_text)

        # collect body inner html
        m = _BODY_RE.search(content)
        if not m:
            raise ValueError(f"Could not find <body>...</body> in {html_path.name}")
        body_inner = m.group(1)

        sections.append(
            f"<section class='report-section' data-source='{html_path.name}'>{body_inner}</section>"
        )

    all_styles_text = "\n".join(all_styles)
    sections_html = "\n".join(sections)

    combined_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />

  <style>
    /* --- Imported styles from each report (inline + linked local CSS) --- */
    {all_styles_text}
  </style>

  <style>
    /* --- Page sizing hints --- */
    @page {{
      size: {pdf_format};
      margin: 12mm 10mm 12mm 10mm;
    }}

    /* --- Combine layout --- */
    .report-section {{
      page-break-after: always;
      break-after: page;
    }}
    .report-section:last-child {{
      page-break-after: auto;
      break-after: auto;
    }}

    /* --- PRINT FIXES (critical) --- */
    @media print {{
      html, body {{
        background: #fff !important;
        margin: 0 !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }}

      /* Many of your reports use a centered ".page" with fixed width/height */
      .page {{
        width: auto !important;
        height: auto !important;
        max-width: none !important;
        max-height: none !important;
        margin: 0 !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        background: #fff !important;
      }}

      /* Disable scroll containers so tables can paginate */
      .table-wrap, .scroll, .scrollable {{
        overflow: visible !important;
        max-height: none !important;
        height: auto !important;
        border: none !important;
      }}

      /* Sticky headers often break print */
      th {{
        position: static !important;
        top: auto !important;
      }}

      /* Better page breaking behavior for tables */
      table {{
        page-break-inside: auto;
        break-inside: auto;
      }}
      tr {{
        page-break-inside: avoid;
        break-inside: avoid;
        page-break-after: auto;
      }}
      thead {{
        display: table-header-group;
      }}
      tfoot {{
        display: table-footer-group;
      }}
    }}
  </style>
</head>

<body>
  {sections_html}
</body>
</html>
"""

    pdf_path = output_dir / combined_pdf_name
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is required for PDF export. Install dependencies and run "
            "`playwright install chromium`."
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # set_content is stable for merged docs and keeps CSS in one DOM
        page.set_content(combined_html, wait_until="load")
        page.emulate_media(media="print")

        page.pdf(
            path=str(pdf_path),
            format=pdf_format,
            print_background=print_background,
            prefer_css_page_size=True,  # honors @page sizing/margins
        )

        browser.close()

    return pdf_path


if __name__ == "__main__":
    out = export_combined_report_pdf(
        output_dir="output",
        combined_pdf_name="combined_report.pdf",
        html_files=("01_exec_summary.html", "02_cost_analysis.html", "03_pivot.html"),
        pdf_format="A4",
        print_background=True,
    )
    print("Wrote:", out)
