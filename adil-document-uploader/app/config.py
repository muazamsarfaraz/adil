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
]


class Settings(BaseSettings):
    # TNA
    tna_base_url: str = "https://caselaw.nationalarchives.gov.uk"
    tna_max_requests_per_minute: int = 150

    # Gemini
    gemini_api_key: str
    file_search_store_id: str

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Auth
    admin_api_key: str

    # Service
    port: int = 8002

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
