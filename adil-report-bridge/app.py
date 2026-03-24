"""
adil-report-bridge — AI-Powered Form Submission Service

Internal microservice that uses browser-use + Gemini Flash to submit
hate crime reports to external reporting portals on behalf of AskAdil users.

Endpoints:
    POST /submit          - Submit a report to a target form
    GET  /health          - Liveness probe
    GET  /health/targets  - Target form reachability (cached 5 min)
    GET  /targets         - Available targets and required fields
"""

import logging
import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from targets import TARGETS, get_target, validate_data_for_target

from models import (
    HealthResponse,
    SubmitRequest,
    SubmitResponse,
    TargetInfo,
)

# Lazy import — browser_agent pulls in browser-use/playwright/langchain which is heavy.
# Importing at module level can cause startup timeouts on Railway.
_submit_report = None


def _get_submit_report():
    global _submit_report
    if _submit_report is None:
        from browser_agent import submit_report

        _submit_report = submit_report
    return _submit_report


load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

VERSION = "0.1.0"

# --- Authentication ---
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY")
api_key_header = APIKeyHeader(name="X-Bridge-Key", auto_error=False)


async def verify_bridge_key(api_key: str = Security(api_key_header)) -> str:
    if not BRIDGE_API_KEY:
        logger.warning("BRIDGE_API_KEY not set — running in OPEN mode")
        return "open"
    if not api_key:
        raise HTTPException(status_code=403, detail="Missing X-Bridge-Key header.")
    if not secrets.compare_digest(api_key, BRIDGE_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid bridge key.")
    return api_key


# --- App ---
app = FastAPI(
    title="adil-report-bridge",
    description="AI-powered form submission service for AskAdil.",
    version=VERSION,
    docs_url=None,
    redoc_url=None,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy", version=VERSION)


_target_health_cache: dict[str, dict] = {}
_target_health_ts: float = 0
TARGET_HEALTH_TTL = 300


@app.get("/health/targets")
async def health_targets(_key: str = Security(verify_bridge_key)):
    global _target_health_cache, _target_health_ts
    now = time.time()

    if now - _target_health_ts < TARGET_HEALTH_TTL and _target_health_cache:
        return {"targets": _target_health_cache}

    import httpx

    results = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for tid, tcfg in TARGETS.items():
            try:
                resp = await client.head(tcfg["url"])
                results[tid] = {
                    "reachable": resp.status_code < 500,
                    "last_checked": time.time(),
                }
            except Exception:
                results[tid] = {"reachable": False, "last_checked": time.time()}

    _target_health_cache = results
    _target_health_ts = now
    return {"targets": results}


@app.get("/targets")
async def list_targets(_key: str = Security(verify_bridge_key)):
    return {
        tid: TargetInfo(
            name=tcfg["name"],
            url=tcfg["url"],
            required_fields=tcfg["required_fields"],
            optional_fields=tcfg["optional_fields"],
            coverage=tcfg["coverage"],
        )
        for tid, tcfg in TARGETS.items()
    }


@app.post("/submit", response_model=SubmitResponse)
async def submit(body: SubmitRequest, _key: str = Security(verify_bridge_key)):
    target = get_target(body.target)
    if not target:
        raise HTTPException(status_code=400, detail=f"Unknown target: {body.target}")

    missing = validate_data_for_target(body.target, body.data)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields for {body.target}: {', '.join(missing)}",
        )

    adapter_type = target.get("adapter_type", "browser")
    logger.info("Submission attempt: target=%s adapter=%s", body.target, adapter_type)

    if adapter_type == "email":
        from email_adapter import send_email_report

        result = await send_email_report(body.target, target, body.data)
    else:
        result = await _get_submit_report()(body.target, body.data)

    logger.info(
        "Submission result: target=%s adapter=%s success=%s ref=%s",
        body.target,
        adapter_type,
        result.get("success"),
        result.get("reference_number", "none"),
    )

    return SubmitResponse(**result)
