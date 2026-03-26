from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "adil-outreach-engine"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/outreach"

    # Auth
    api_key: str = "change-me-in-production"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
