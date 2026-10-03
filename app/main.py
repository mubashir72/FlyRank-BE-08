import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import ReportArtifact
from app.schemas import ReportCreate, ReportResponse
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
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_report(payload: ReportCreate, db: DbSession) -> ReportResponse:
    existing = db.scalar(
        select(ReportArtifact).where(
            ReportArtifact.start_date == payload.start_date,
            ReportArtifact.end_date == payload.end_date,
        )
    )
    if existing is not None and _artifact_exists(existing):
        return ReportResponse.from_artifact(existing)

    try:
        report = get_report_data(db, payload.start_date, payload.end_date)
        pdf_bytes = render_sales_report(report, payload.start_date, payload.end_date)
        artifact_dir = Path(settings.artifact_dir).resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / (
            f"sales-report-{payload.start_date.isoformat()}-{payload.end_date.isoformat()}.pdf"
        )
        temporary_path = artifact_dir / f".{uuid4()}.tmp"
        temporary_path.write_bytes(pdf_bytes)
        os.replace(temporary_path, artifact_path)

        if existing is None:
            existing = ReportArtifact(
                start_date=payload.start_date,
                end_date=payload.end_date,
                artifact_path=str(artifact_path),
            )
            db.add(existing)
        else:
            existing.artifact_path = str(artifact_path)
        db.commit()
        db.refresh(existing)
        return ReportResponse.from_artifact(existing)
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(
            select(ReportArtifact).where(
                ReportArtifact.start_date == payload.start_date,
                ReportArtifact.end_date == payload.end_date,
            )
        )
        if existing is not None and _artifact_exists(existing):
            return ReportResponse.from_artifact(existing)
        logger.exception("Concurrent report generation could not be resolved")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "report_conflict",
                "message": "A report for this date range is being generated.",
            },
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Report generation failed for %s through %s",
            payload.start_date,
            payload.end_date,
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
    artifact = db.get(ReportArtifact, report_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Report was not found."},
        )
    return ReportResponse.from_artifact(artifact)


@app.get("/reports/{report_id}/download")
def download_report(report_id: str, db: DbSession) -> FileResponse:
    artifact = db.get(ReportArtifact, report_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": "Report was not found."},
        )
    if not _artifact_exists(artifact):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "code": "report_artifact_unavailable",
                "message": "The report file is no longer available.",
            },
        )
    return FileResponse(
        artifact.artifact_path,
        media_type="application/pdf",
        filename=Path(artifact.artifact_path).name,
    )


@app.get("/reports", response_model=list[ReportResponse])
def list_reports(
    db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[ReportResponse]:
    artifacts = db.scalars(
        select(ReportArtifact)
        .order_by(ReportArtifact.created_at.desc())
        .limit(limit)
    )
    return [ReportResponse.from_artifact(artifact) for artifact in artifacts]


def _artifact_exists(artifact: ReportArtifact) -> bool:
    path = Path(artifact.artifact_path).resolve()
    artifact_root = Path(settings.artifact_dir).resolve()
    if path.parent != artifact_root:
        logger.error("Report artifact path is outside configured storage: %s", path)
        return False
    return path.is_file()
