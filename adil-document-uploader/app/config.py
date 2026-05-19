from __future__ import annotations

from dataclasses import dataclass
from pydantic_settings import BaseSettings


@dataclass(frozen=True)
class SearchDomain:
    """A predefined case law search domain."""

    name: str
    queries: list[str]
    courts: list[str]


SEARCH_DOMAINS: list[SearchDomain] = [
    SearchDomain(
        name="religious_discrimination_employment",
        queries=['"religious discrimination"', '"Equality Act" religion belief'],
        courts=["eat", "ewca/civ"],
    ),
    SearchDomain(
        name="hate_crime_religious_hatred",
        queries=['"religiously aggravated"', '"religious hatred"', '"racially aggravated"'],
        courts=["ewca/crim", "ewhc/admin"],
    ),
    SearchDomain(
        name="goods_services_discrimination",
        queries=['"discrimination" "provision of services"', '"Equality Act" "section 29"'],
        courts=["ewca/civ", "ewhc/admin"],
    ),
    SearchDomain(
        name="intersectional_race_religion",
        queries=['"race discrimination" Muslim', '"ethnic origin" discrimination'],
        courts=["eat", "ewca/civ"],
    ),
    SearchDomain(
        name="echr_human_rights",
        queries=['"Article 9" religion', '"Article 14" discrimination'],
        courts=["uksc", "ewca/civ"],
    ),
    # Mental Capacity Act / Court of Protection track — added 2026-04-23 following
    # community queries about deputyship for young adults with learning disabilities.
    # EWCOP (Court of Protection) is the primary court; UKSC covers landmark cases
    # like Cheshire West [2014] UKSC 19 and JB [2021] UKSC 52.
    SearchDomain(
        name="mental_capacity_deputyship",
        queries=[
            '"Mental Capacity Act" 2005',
            '"best interests" deputyship',
            '"deprivation of liberty"',
            '"Court of Protection" welfare',
            '"learning disability" capacity',
        ],
        courts=["ewcop", "uksc", "ewca/civ"],
    ),
]


class Settings(BaseSettings):
    # TNA
    tna_base_url: str = "https://caselaw.nationalarchives.gov.uk"
    tna_max_requests_per_minute: int = 150

    # Gemini
    gemini_api_key: str
    file_search_store_id: str

    # Anthropic (Claude Haiku 4.5 — OG-RAG extraction pass 2). Worker-only.
    # API service can leave unset; the worker raises at pass-2 call time when
    # missing. Org-level key from console.anthropic.com — separate from any
    # Claude Code billing key. See CLAUDE.md for rotation guidance.
    anthropic_api_key: str | None = None

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Auth
    admin_api_key: str

    # Telegram heartbeat (optional — heartbeat disabled if unset)
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # RAG API (for full-pipeline keep-alive query)
    rag_api_url: str = "https://adil-rag-api-production.up.railway.app"
    rag_api_key: str | None = None

    # Health check targets (comma-separated name=url pairs)
    heartbeat_targets: str = (
        "rag-api=https://adil-rag-api-production.up.railway.app/health,"
        "frontend=https://askadil.org,"
        "doc-uploader=https://adil-document-uploader-production.up.railway.app/health,"
        "outreach-engine=https://adil-outreach-engine-production.up.railway.app/"
    )

    # Service
    port: int = 8002

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
