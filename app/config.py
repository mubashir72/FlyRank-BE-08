from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_path: Path = Path("report.db")
    artifact_dir: str = "artifacts"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
