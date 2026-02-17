# ITB Report Web/API Service

## Run locally

1. Create/activate virtual env.
2. Install deps:

```bash
pip install -r requirements.txt
playwright install chromium
```

3. Start API:

```bash
uvicorn app.api:app --reload --port 8000
```

4. Open UI:

- [http://localhost:8000](http://localhost:8000)

## Endpoint examples

Generate report:

```bash
curl -X POST http://localhost:8000/api/reports \
  -F "file=@/absolute/path/ITB15 - Summary R0.xlsx" \
  -F "email=person@company.com"
```

Send email later:

```bash
curl -X POST http://localhost:8000/api/reports/<report_id>/email \
  -H "Content-Type: application/json" \
  -d '{"email":"person@company.com"}'
```

Download artifact:

```bash
curl -L "http://localhost:8000/api/reports/<report_id>/artifact/ITB15_combined_report.pdf" -o report.pdf
```

## Notes

- Generated files are stored under `/Users/serankobaner/summary_automate/runs/<report_id>/`.
- Email requires SMTP env vars configured (`SMTP_HOST`, `EMAIL_FROM`, etc.).
