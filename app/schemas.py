from datetime import date, datetime, timedelta
from pydantic import BaseModel, Field, model_validator

from app.models import ReportArtifact


class ReportCreate(BaseModel):
    start_date: date = Field(default_factory=lambda: date.today() - timedelta(days=29))
    end_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def validate_date_range(self) -> "ReportCreate":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class ReportResponse(BaseModel):
    id: str
    start_date: date
    end_date: date
    created_at: datetime
    download_url: str

    @classmethod
    def from_artifact(cls, artifact: ReportArtifact) -> "ReportResponse":
        return cls(
            id=artifact.id,
            start_date=artifact.start_date,
            end_date=artifact.end_date,
            created_at=artifact.created_at,
            download_url=f"/reports/{artifact.id}/download",
        )
