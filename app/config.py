from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://report:report@localhost:5432/reports"
    artifact_dir: str = "artifacts"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
