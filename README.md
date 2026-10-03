# Sales report pipeline

A FastAPI service that performs one SQL aggregation, renders an HTML report to a
real PDF with Playwright Chromium, saves the artifact to disk, and returns a
download link. Report generation runs synchronously in the request, as required
by the workshop. Requesting the same date range again reuses its stored PDF.

## Run with Docker Compose

Docker Compose starts PostgreSQL and the API. The image installs Chromium and
its system dependencies during the build.

```powershell
docker compose up --build
docker compose exec api python -m app.seed_data
```

The API is at `http://localhost:8000`; interactive docs are at
`http://localhost:8000/docs`. The fictional seed dataset contains 200 line items across 100 orders and five
products. It is inserted only when the sales table is empty, so rerunning the
seed command is safe.

The credentials in `compose.yaml` are for local development only. Do not expose
the Compose services publicly or reuse those credentials in production.

## Run locally

Install Python 3.10+ and PostgreSQL, then copy `.env.example` to `.env` and
create the database configured by `DATABASE_URL`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r dev-requirements.txt
python -m playwright install chromium
python -m app.seed_data
uvicorn app.main:app --reload
```

## Generate and download a report

`POST /reports` accepts optional inclusive ISO date bounds. Without them, the
report covers the latest 30 calendar days, including today.

```powershell
curl.exe -X POST http://localhost:8000/reports `
  -H "Content-Type: application/json" `
  -d "{}"
```

The response includes `id` and `download_url`. Open the URL or download it:

```powershell
curl.exe -L http://localhost:8000/reports/REPORT_ID/download `
  -o sales-report.pdf
```

For a specific period:

```json
{"start_date":"2026-09-01","end_date":"2026-09-30"}
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness checkpoint |
| `GET` | `/health/ready` | Database readiness |
| `POST` | `/reports` | Generate a report synchronously and return its link |
| `GET` | `/reports` | List recent generated reports (optional `limit`, 1-100) |
| `GET` | `/reports/{id}` | Look up a report and its download URL |
| `GET` | `/reports/{id}/download` | Download the saved PDF |

The report includes orders, units sold, revenue, average order value, and
distinct products. SQL calculates all five metrics in one statement. The API
stores the PDF path and date range in PostgreSQL; the file bytes are never
embedded in API metadata. Unique date-range records and deterministic artifact
names keep repeated requests from creating duplicate reports.

Scheduled or background generation is optional workshop stretch work and is
not enabled by default.

## Tests

```powershell
python -m pytest
```
