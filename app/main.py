import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import Report
from app.schemas import ReportCreate, ReportCreated, ReportResponse
from app.services.sales_reports import get_report_data, render_sales_report

logger = logging.getLogger(__name__)
DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    Path(settings.artifact_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Sales Report Pipeline",
    description="Aggregate sales, render a PDF, store it, and return a download link.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database readiness check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "message": "The database is unavailable.",
            },
        ) from exc
    return {"status": "ready"}


@app.post(
    "/reports",
    response_model=ReportCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    db: DbSession,
    response: Response,
    payload: Annotated[ReportCreate | None, Body()] = None,
) -> ReportCreated:
    request = payload or ReportCreate()
    report_id = str(uuid4())
    report_dir = Path(settings.artifact_dir).resolve()
    report_path = report_dir / f"{report_id}.pdf"
    temporary_path = report_dir / f".{report_id}.tmp.pdf"
    try:
        if not request.force:
            if db.get_bind().dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            existing_reports = db.scalars(
                select(Report)
                .where(func.date(Report.created_at) == date.today().isoformat())
                .order_by(Report.created_at.desc())
            )
            for existing in existing_reports:
                existing_path = _report_path(existing)
                if existing_path is not None and existing_path.is_file():
                    db.rollback()
                    response.status_code = status.HTTP_200_OK
                    return ReportCreated(
                        id=existing.id,
                        file=f"/reports/{existing.id}/file",
                    )

        report_dir.mkdir(parents=True, exist_ok=True)
        report = get_report_data(db, request.start_date, request.end_date)
        render_sales_report(
            report,
            request.start_date,
            request.end_date,
            output_path=temporary_path,
        )
        os.replace(temporary_path, report_path)
        record = Report(id=report_id, path=report_path.name)
        db.add(record)
        db.commit()
        return ReportCreated(id=record.id, file=f"/reports/{record.id}/file")
    except Exception as exc:
        db.rollback()
        temporary_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        logger.exception(
            "Report generation failed for %s through %s",
            request.start_date,
            request.end_date,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "report_generation_failed",
                "message": "The report could not be generated.",
            },
        ) from exc


@app.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, db: DbSession) -> ReportResponse:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Report was not found."},
        )
    return ReportResponse.from_report(report)


@app.get("/reports/{report_id}/file")
@app.get("/reports/{report_id}/download", include_in_schema=False)
def download_report(report_id: str, db: DbSession) -> FileResponse:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Report was not found."},
        )
    report_path = _report_path(report)
    if report_path is None or not report_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "code": "report_file_unavailable",
                "message": "The report file is no longer available.",
            },
        )
    return FileResponse(
        report_path,
        media_type="application/pdf",
        filename=report_path.name,
    )


@app.get("/reports", response_model=list[ReportResponse])
def list_reports(
    db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[ReportResponse]:
    reports = db.scalars(
        select(Report)
        .order_by(Report.created_at.desc())
        .limit(limit)
    )
    return [ReportResponse.from_report(report) for report in reports]


def _report_path(report: Report) -> Path | None:
    relative_path = Path(report.path)
    if relative_path.name != report.path or relative_path.suffix.lower() != ".pdf":
        logger.error("Invalid report path in database: %s", report.path)
        return None
    report_dir = Path(settings.artifact_dir).resolve()
    path = (report_dir / relative_path).resolve()
    if path.parent != report_dir:
        logger.error("Report path is outside configured storage: %s", path)
        return None
    return path
