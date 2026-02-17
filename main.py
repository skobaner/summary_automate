# main.py
from dataclasses import dataclass
from pathlib import Path

from read_summary_df import (
    load_summary_df,
    select_spend_tail_cbc_codes,
    get_cost_analysis_for_codes,
)
from compute_metrics import compute_cost_metrics
from render_exec_summary import generate_exec_summary
from read_itb4_df import load_itb4_df, build_itb4_pivot
from render_pivot_html import write_pivot_html
from render_cost_analysis_html import render_cost_analysis_html
from html_to_pdf import export_combined_report_pdf


OUTPUT_DIR = Path("output")
PERCENTILE_TAIL = 10.0


@dataclass(frozen=True)
class PipelineContext:
    itb: str
    selected_codes: list[str]
    cbc_description: object
    metrics: dict
    cost_analysis_df: object
    pivot_df: object


def build_pipeline_context() -> PipelineContext:
    summary_df, itb, _ = load_summary_df()
    metrics = compute_cost_metrics(summary_df, itb)

    tails = select_spend_tail_cbc_codes(
        summary_df,
        bottom_pct=PERCENTILE_TAIL,
        top_pct=PERCENTILE_TAIL,
    )
    bottom = tails["bottom"]
    top = tails["top"]
    selected_codes = tails["selected_codes"]
    cbc_description = tails["cbc_description"]

    print("Bottom threshold:", bottom["threshold"])
    print("Bottom CBC codes:", bottom["codes"])
    print("Top threshold:", top["threshold"])
    print("Top CBC codes:", top["codes"])
    print("Selected CBC codes:", selected_codes)
    print("CBC Description mapping:", cbc_description)

    cost_analysis_df = get_cost_analysis_for_codes(summary_df, selected_codes)
    df_itb4, _, _ = load_itb4_df(itb=itb)
    print("Loaded ITB4 df:", df_itb4.shape)

    pivot_df = build_itb4_pivot(
        df_itb4,
        itb=itb,
        selected_codes=selected_codes,
        cbc_description=cbc_description,
        drop_all_zero_rows=True,
    )

    return PipelineContext(
        itb=itb,
        selected_codes=selected_codes,
        cbc_description=cbc_description,
        metrics=metrics,
        cost_analysis_df=cost_analysis_df,
        pivot_df=pivot_df,
    )


def write_exec_summary(metrics: dict, output_dir: Path) -> Path:
    generated_path = Path(generate_exec_summary(metrics, output_dir=output_dir))
    canonical_path = output_dir / "01_exec_summary.html"
    if generated_path.resolve() == canonical_path.resolve():
        return generated_path
    canonical_path.write_text(generated_path.read_text(encoding="utf-8"), encoding="utf-8")
    return canonical_path


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    ctx = build_pipeline_context()
    ctx.cost_analysis_df.to_csv(OUTPUT_DIR / f"itb{ctx.itb}_cost_analysis.csv", index=False)

    # -------------------------
    # 5) Write HTML outputs (01/02/03 order = Exec, Cost, Pivot)
    # -------------------------
    exec_html = write_exec_summary(ctx.metrics, OUTPUT_DIR)
    print("Wrote:", exec_html)

    cost_html = render_cost_analysis_html(
        ctx.cost_analysis_df,
        OUTPUT_DIR / "02_cost_analysis.html",
        title=f"ITB{ctx.itb} Cost Analysis (Selected CBS Codes)",
        subtitle="From Summary billing sheet. Includes Budget vs Cumulative and % Spent.",
    )
    print("Wrote:", cost_html)

    pivot_html = write_pivot_html(
        ctx.pivot_df,
        output_path=OUTPUT_DIR / "03_pivot.html",
        title=f"ITB{ctx.itb} Pivot (Selected CBS Codes)",
        subtitle=f"Rows: CBC — DESCRIPTION | Columns: ITB{ctx.itb}A/F2/F3/F4 | Values: Sum of Total Cost",
    )
    print("Wrote:", pivot_html)

    # -------------------------
    # 6) Combine into ONE PDF (exec + cost + pivot)
    # -------------------------
    pdf = export_combined_report_pdf(
        output_dir=OUTPUT_DIR,
        combined_pdf_name=f"ITB{ctx.itb}_combined_report.pdf",
        html_files=("01_exec_summary.html", "02_cost_analysis.html", "03_pivot.html"),
        pdf_format="A4",
        print_background=True,
    )
    print("Combined PDF written:", pdf)


if __name__ == "__main__":
    main()
