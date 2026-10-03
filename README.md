# Sales report pipeline

A FastAPI service that aggregates a small SQLite orders database, renders an
HTML report to PDF with Playwright Chromium, saves the PDF to disk, and returns
a download link. Report generation is synchronous, as required by the workshop.
Repeated requests for the same date range reuse the saved report.

## Dataset

Option A uses Python's built-in `sqlite3` module. The seed script creates
`report.db` with an `orders` table (`id`, `customer`, `product`, `amount`,
`created_at`) and 200 fictional orders across six products, dated within the
last 30 days. Each seed run deletes existing orders before inserting a fresh
set, so running it repeatedly always leaves exactly 200 rows. The initial
seeded `report.db` is committed as the Stage 1 checkpoint; rerun the script to
replace its sample data.

```powershell
python -m app.seed_data
python -c "import sqlite3; db=sqlite3.connect('report.db'); print(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0])"
python -m app.seed_data
python -c "import sqlite3; db=sqlite3.connect('report.db'); print(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0])"
```

Both count checks print `200`.

## Run locally

Install Python 3.10+ and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r dev-requirements.txt
python -m playwright install chromium
python -m app.seed_data
uvicorn app.main:app --reload
```

The API is at `http://localhost:8000`; interactive docs are at
`http://localhost:8000/docs`.

## Run with Docker Compose

```powershell
docker compose up --build
docker compose exec api python -m app.seed_data
```

SQLite and PDF files are persisted in Compose volumes. Seed data is fictional.

## Generate and download a report

`POST /reports` synchronously aggregates the latest 30 calendar days, renders
the PDF, saves it under `reports/`, and records its ID, relative file path, and
creation time in the `reports` table. Optional inclusive ISO date bounds can be
provided.

```powershell
curl.exe -X POST http://localhost:8000/reports `
  -H "Content-Type: application/json" `
  -d "{}"
```

The response includes `id` and `file`. Download the PDF from that link:

```powershell
curl.exe -L http://localhost:8000/reports/REPORT_ID/file `
  -o sales-report.pdf
```

`GET /reports/{id}` returns the stored report row and its file link. An unknown
ID returns `404`.

For a specific period:

```json
{"start_date":"2026-09-01","end_date":"2026-09-30"}
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness checkpoint |
| `GET` | `/health/ready` | SQLite readiness |
| `POST` | `/reports` | Generate a report and return its download link |
| `GET` | `/reports` | List recent reports (optional `limit`, 1-100) |
| `GET` | `/reports/{id}` | Look up a report and its download URL |
| `GET` | `/reports/{id}/file` | Download the saved PDF |

The report data includes total orders, total revenue, the five highest-revenue
products, order counts for each of the latest seven days, and all order rows.
Print the aggregated data as JSON without rendering a PDF:

```powershell
python -m scripts.print_report
```

Render the current dataset into a multi-page PDF with the full order table:

```powershell
python -m scripts.render_test_report
```

This saves `reports/test.pdf`. The detailed table repeats its header on each
printed page and keeps each order row together across page breaks.

The API stores each PDF's relative path in SQLite; file bytes stay on disk.
Move report generation to a background job when reports take long enough to
risk request timeouts or when concurrent report requests noticeably consume
API capacity.

Scheduled or background generation is optional workshop stretch work and is
not enabled by default.

## Tests

```powershell
python -m pytest
```
