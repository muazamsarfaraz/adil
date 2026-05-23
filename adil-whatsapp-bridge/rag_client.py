"""
rag_client.py — thin async wrapper around adil-rag-api's /api/v1/query endpoint.

We use the non-streaming variant since WhatsApp delivers whole messages.
The conversation_history we pass mirrors the rag-api QueryRequest schema:
each turn has ``role`` ('user' | 'model') and ``content``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 45.0  # Sonnet RAG can take ~10–25s


class RagClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def query(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        max_sources: int = 5,
        include_viability: bool = True,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/query"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if client_ip:
            headers["X-AskAdil-Client-IP"] = client_ip
        body: dict[str, Any] = {
            "query": question[:10000],
            "max_sources": max_sources,
            "include_viability_score": include_viability,
        }
        if history:
            body["conversation_history"] = history[-50:]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
        if resp.status_code >= 400:
            logger.warning("rag-api %s: %s", resp.status_code, resp.text[:400])
            resp.raise_for_status()
        return resp.json()


def from_env() -> RagClient | None:
    base = os.environ.get("RAG_API_URL")
    key = os.environ.get("RAG_API_KEY")
    if not base or not key:
        return None
    return RagClient(base, key)
