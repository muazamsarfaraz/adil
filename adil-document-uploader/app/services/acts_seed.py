"""Hard-coded seed list of UK Acts that AskAdil cites today.

Mirrors the ``UK_LEGISLATION_URLS`` dict in ``adil-rag-api/rag_service.py``.
Kept in this repo so the uploader-worker doesn't need to import from the
RAG API codebase. Extend by adding entries here, not by editing rag-api.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActSeed:
    name: str
    url: str  # legislation.gov.uk base URL


UK_ACTS_SEED: list[ActSeed] = [
    ActSeed("Equality Act 2010", "https://www.legislation.gov.uk/ukpga/2010/15"),
    ActSeed("Public Order Act 1986", "https://www.legislation.gov.uk/ukpga/1986/64"),
    ActSeed("Crime and Disorder Act 1998", "https://www.legislation.gov.uk/ukpga/1998/37"),
    ActSeed("Online Safety Act 2023", "https://www.legislation.gov.uk/ukpga/2023/50"),
    ActSeed("Human Rights Act 1998", "https://www.legislation.gov.uk/ukpga/1998/42"),
    ActSeed("Employment Rights Act 1996", "https://www.legislation.gov.uk/ukpga/1996/18"),
    ActSeed("Racial and Religious Hatred Act 2006", "https://www.legislation.gov.uk/ukpga/2006/1"),
    ActSeed("Disability Discrimination Act 1995", "https://www.legislation.gov.uk/ukpga/1995/50"),
    ActSeed("Mental Capacity Act 2005", "https://www.legislation.gov.uk/ukpga/2005/9"),
    # Scotland-specific
    ActSeed(
        "Hate Crime and Public Order (Scotland) Act 2021",
        "https://www.legislation.gov.uk/asp/2021/14",
    ),
    # Northern Ireland-specific
    ActSeed(
        "Fair Employment and Treatment (Northern Ireland) Order 1998",
        "https://www.legislation.gov.uk/nisi/1998/3162",
    ),
    ActSeed(
        "Race Relations (Northern Ireland) Order 1997",
        "https://www.legislation.gov.uk/nisi/1997/869",
    ),
]
