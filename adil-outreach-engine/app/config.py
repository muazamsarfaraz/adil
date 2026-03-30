from pydantic import field_validator
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

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Cal.com
    cal_api_key: str = ""
    cal_webhook_secret: str = ""

    # Public
    public_base_url: str = "http://localhost:8001"

    # Redis (for rate limiting / arq)
    redis_url: str = "redis://localhost:6379"

    # SendGrid
    sendgrid_api_key: str = ""
    sendgrid_webhook_verification_key: str = ""
    sendgrid_webhook_verify_enabled: bool = True

    # LLM API keys
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Server — Railway provides PORT; fall back to 8001 for local dev
    host: str = "0.0.0.0"
    port: int = 8001

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Handle Railway's DATABASE_URL format (postgresql:// without +asyncpg)."""
        if v and v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
