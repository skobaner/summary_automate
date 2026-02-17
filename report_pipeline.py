from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from compute_metrics import compute_cost_metrics
from html_to_pdf import export_combined_report_pdf
from read_itb4_df import build_itb4_pivot, load_itb4_df
from read_summary_df import (
    get_cost_analysis_for_codes,
    load_summary_df,
    select_spend_tail_cbc_codes,
)
from render_cost_analysis_html import render_cost_analysis_html
from render_exec_summary import generate_exec_summary
from render_pivot_html import write_pivot_html


DEFAULT_TAIL_PERCENT = 10.0


@dataclass(frozen=True)
class ReportArtifacts:
    itb: str
    output_dir: Path
    exec_html: Path
    cost_html: Path
    pivot_html: Path
    pdf_path: Path
    cost_csv: Path


def _write_exec_summary(metrics: dict, output_dir: Path) -> Path:
    generated_path = Path(generate_exec_summary(metrics, output_dir=output_dir))
    canonical_path = output_dir / "01_exec_summary.html"
    if generated_path.resolve() == canonical_path.resolve():
        return generated_path
    canonical_path.write_text(generated_path.read_text(encoding="utf-8"), encoding="utf-8")
    return canonical_path


def generate_report_from_workbook(
    workbook_path: str | Path,
    output_dir: str | Path,
    *,
    tail_percent: float = DEFAULT_TAIL_PERCENT,
    explicit_itb: str | int | None = None,
) -> ReportArtifacts:
    """Generate all report artifacts from a single uploaded workbook."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    summary_df, itb, _ = load_summary_df(
        filepath=workbook_path,
        itb=explicit_itb,
    )
    metrics = compute_cost_metrics(summary_df, itb)

    tails = select_spend_tail_cbc_codes(
        summary_df,
        bottom_pct=tail_percent,
        top_pct=tail_percent,
    )
    selected_codes: list[str] = tails["selected_codes"]
    cbc_description = tails["cbc_description"]

    cost_analysis_df = get_cost_analysis_for_codes(summary_df, selected_codes)
    cost_csv = output_path / f"itb{itb}_cost_analysis.csv"
    cost_analysis_df.to_csv(cost_csv, index=False)

    df_itb4, _, _ = load_itb4_df(filepath=workbook_path, itb=itb)
    pivot_df = build_itb4_pivot(
        df_itb4,
        itb=itb,
        selected_codes=selected_codes,
        cbc_description=cbc_description,
        drop_all_zero_rows=True,
    )

    exec_html = _write_exec_summary(metrics, output_path)
    cost_html = render_cost_analysis_html(
        cost_analysis_df,
        output_path / "02_cost_analysis.html",
        title=f"ITB{itb} Cost Analysis (Selected CBS Codes)",
        subtitle="From Summary billing sheet. Includes Budget vs Cumulative and % Spent.",
    )
    pivot_html = write_pivot_html(
        pivot_df,
        output_path=output_path / "03_pivot.html",
        title=f"ITB{itb} Pivot (Selected CBS Codes)",
        subtitle=f"Rows: CBC - DESCRIPTION | Columns: ITB{itb}A/F2/F3/F4 | Values: Sum of Total Cost",
    )

    pdf_path = export_combined_report_pdf(
        output_dir=output_path,
        combined_pdf_name=f"ITB{itb}_combined_report.pdf",
        html_files=("01_exec_summary.html", "02_cost_analysis.html", "03_pivot.html"),
        pdf_format="A4",
        print_background=True,
    )

    return ReportArtifacts(
        itb=itb,
        output_dir=output_path,
        exec_html=Path(exec_html),
        cost_html=Path(cost_html),
        pivot_html=Path(pivot_html),
        pdf_path=Path(pdf_path),
        cost_csv=cost_csv,
    )


def build_embedded_email_html(artifacts: ReportArtifacts) -> str:
    """Create one email-safe HTML body by concatenating generated sections."""
    return build_embedded_email_html_from_paths(
        itb=artifacts.itb,
        exec_html=artifacts.exec_html,
        cost_html=artifacts.cost_html,
        pivot_html=artifacts.pivot_html,
    )


_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL)


def _body_content(html_text: str) -> str:
    match = _BODY_RE.search(html_text)
    if not match:
        return html_text
    return match.group(1)


def build_embedded_email_html_from_paths(
    *,
    itb: str,
    exec_html: str | Path,
    cost_html: str | Path,
    pivot_html: str | Path,
) -> str:
    """Create one email-safe HTML body from generated section files."""
    sections = []
    for label, path in [
        ("Executive Summary", Path(exec_html)),
        ("Cost Analysis", Path(cost_html)),
        ("Pivot", Path(pivot_html)),
    ]:
        html_text = path.read_text(encoding="utf-8")
        sections.append(
            f"<h2 style='font-family:Arial,sans-serif'>{label}</h2>"
            f"<div>{_body_content(html_text)}</div>"
        )

    return (
        "<html><body style='font-family:Arial,sans-serif'>"
        f"<p>Automated ITB report for ITB{itb}.</p>"
        + "<hr/>".join(sections)
        + "</body></html>"
    )
