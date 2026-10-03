from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from app.models import Report


class ReportCreate(BaseModel):
    start_date: date = Field(
        default_factory=lambda: date.today() - timedelta(days=29)
    )
    end_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def validate_date_range(self) -> "ReportCreate":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class ReportCreated(BaseModel):
    id: str
    file: str


class ReportResponse(BaseModel):
    id: str
    path: str
    created_at: datetime
    file: str

    @classmethod
    def from_report(cls, report: Report) -> "ReportResponse":
        return cls(
            id=report.id,
            path=report.path,
            created_at=report.created_at,
            file=f"/reports/{report.id}/file",
        )
