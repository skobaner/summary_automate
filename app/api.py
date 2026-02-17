from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.email_service import EmailConfigurationError, send_report_email
from report_pipeline import (
    build_embedded_email_html_from_paths,
    generate_report_from_workbook,
)


BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "runs"
STATIC_DIR = BASE_DIR / "app" / "static"

RUNS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ITB Report API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EmailRequest(BaseModel):
    email: str


def _safe_filename(filename: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename).strip("_")
    return sanitized or "uploaded.xlsx"


def _is_valid_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def _meta_path(report_id: str) -> Path:
    return RUNS_DIR / report_id / "meta.json"


def _load_meta(report_id: str) -> dict:
    meta_path = _meta_path(report_id)
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _save_meta(report_id: str, payload: dict) -> None:
    run_dir = RUNS_DIR / report_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _meta_path(report_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _send_email_for_report(report_id: str, email: str) -> None:
    meta = _load_meta(report_id)
    run_dir = RUNS_DIR / report_id

    pdf_path = run_dir / meta["pdf_file"]
    exec_html = run_dir / meta["exec_html"]
    cost_html = run_dir / meta["cost_html"]
    pivot_html = run_dir / meta["pivot_html"]

    html_body = build_embedded_email_html_from_paths(
        itb=meta["itb"],
        exec_html=exec_html,
        cost_html=cost_html,
        pivot_html=pivot_html,
    )

    send_report_email(
        to_email=email,
        subject=f"ITB{meta['itb']} Automated Report",
        html_body=html_body,
        attachments=[pdf_path],
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/reports")
async def create_report(
    file: UploadFile = File(...),
    email: str | None = Form(default=None),
    itb: str | None = Form(default=None),
) -> dict:
    report_id = str(uuid.uuid4())
    run_dir = RUNS_DIR / report_id
    run_dir.mkdir(parents=True, exist_ok=True)

    upload_name = _safe_filename(file.filename or "uploaded.xlsx")
    upload_path = run_dir / upload_name

    with upload_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        artifacts = await run_in_threadpool(
            generate_report_from_workbook,
            upload_path,
            run_dir,
            explicit_itb=itb,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Report generation failed: {exc}") from exc

    metadata = {
        "report_id": report_id,
        "itb": artifacts.itb,
        "source_file": upload_name,
        "pdf_file": artifacts.pdf_path.name,
        "exec_html": artifacts.exec_html.name,
        "cost_html": artifacts.cost_html.name,
        "pivot_html": artifacts.pivot_html.name,
    }
    _save_meta(report_id, metadata)

    emailed = False
    email_error = None
    if email:
        if not _is_valid_email(email):
            email_error = "Invalid email address format."
            return {
                **metadata,
                "emailed": emailed,
                "email_error": email_error,
                "download_url": f"/api/reports/{report_id}/artifact/{artifacts.pdf_path.name}",
            }
        try:
            _send_email_for_report(report_id, str(email))
            emailed = True
        except EmailConfigurationError as exc:
            email_error = str(exc)
        except Exception as exc:
            email_error = f"Email send failed: {exc}"

    return {
        **metadata,
        "emailed": emailed,
        "email_error": email_error,
        "download_url": f"/api/reports/{report_id}/artifact/{artifacts.pdf_path.name}",
    }


@app.post("/api/reports/{report_id}/email")
def send_report(report_id: str, req: EmailRequest) -> dict:
    if not _is_valid_email(req.email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")
    try:
        _send_email_for_report(report_id, str(req.email))
    except EmailConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Email send failed: {exc}") from exc
    return {"report_id": report_id, "emailed": True}


@app.get("/api/reports/{report_id}/artifact/{filename}")
def get_artifact(report_id: str, filename: str) -> FileResponse:
    run_dir = RUNS_DIR / report_id
    target = run_dir / _safe_filename(filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path=target)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
