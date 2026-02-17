# Azure Deployment Plan

## Recommended architecture

- **Azure Container Apps** (single container) hosts FastAPI backend + static frontend.
- **Azure Container Registry (ACR)** stores container image.
- **Azure Blob Storage** (future enhancement) can store generated artifacts instead of local disk.
- **Azure Communication Services Email** or SMTP relay sends report emails.
- **Optional later**: split frontend to Azure Static Web Apps and keep API in Container Apps.

This design gives:
- A direct HTTP API endpoint for non-frontend callers.
- A built-in upload UI for business users.
- Easy horizontal scale for report generation.

## API surface

- `POST /api/reports`
  - multipart form:
    - `file` (required): ITB workbook
    - `email` (optional): send email immediately
    - `itb` (optional): ITB override
- `POST /api/reports/{report_id}/email`
  - JSON body: `{ "email": "user@company.com" }`
- `GET /api/reports/{report_id}/artifact/{filename}`
  - downloads generated files (PDF/HTML/CSV)
- `GET /health`

## Email configuration

Set these env vars in Container Apps:

- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_USE_TLS` (`true`/`false`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`

## Deploy steps (CLI)

1. Build and push image:

```bash
az acr login --name <acr_name>
docker build -t <acr_name>.azurecr.io/itb-report-api:latest .
docker push <acr_name>.azurecr.io/itb-report-api:latest
```

2. Create Container App Environment + App (first time):

```bash
az containerapp env create \
  --name <env_name> \
  --resource-group <rg> \
  --location eastus

az containerapp create \
  --name itb-report-api \
  --resource-group <rg> \
  --environment <env_name> \
  --image <acr_name>.azurecr.io/itb-report-api:latest \
  --target-port 8000 \
  --ingress external \
  --registry-server <acr_name>.azurecr.io \
  --cpu 1.0 --memory 2.0Gi
```

3. Set env vars:

```bash
az containerapp update \
  --name itb-report-api \
  --resource-group <rg> \
  --set-env-vars \
    SMTP_HOST=<smtp_host> \
    SMTP_PORT=587 \
    SMTP_USE_TLS=true \
    SMTP_USERNAME=<smtp_user> \
    SMTP_PASSWORD=<smtp_password> \
    EMAIL_FROM=<from_email>
```

4. Browse app URL:

```bash
az containerapp show \
  --name itb-report-api \
  --resource-group <rg> \
  --query properties.configuration.ingress.fqdn -o tsv
```

## System design notes

- Uploaded files and generated artifacts are currently kept on local container disk under `runs/`.
- For production durability and multi-instance scale, move artifacts to Blob Storage and store metadata in Cosmos DB or PostgreSQL.
- For high throughput, split generation into async jobs (queue + worker) and return a status endpoint.
