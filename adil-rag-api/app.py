"""
Project Adil - RAG API Backend (AskAdil)
UK Discrimination Law Knowledge Base

FastAPI backend for the AskAdil legal assistant.

Endpoints:
    /api/v1/query   - Multi-turn legal Q&A with RAG
    /api/v1/analyze - Content extraction and legal analysis of URLs
    /health         - Liveness / readiness probe
    /stats          - Runtime statistics (uptime, request counts)

Features:
    - Conversation history (multi-turn context via ConversationTurn)
    - Content extraction from YouTube, Facebook, Twitter/X, Instagram, webpages
    - Actionable next steps and resource directory in responses
    - Litigation viability detection with Vento bands

Security:
    - API key authentication (X-API-Key header)
    - Per-key rate limiting
    - SSRF protection on all outbound URL fetches
    - Input validation with max_length constraints
"""

import asyncio
import base64
import binascii
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from geolocation import detect_jurisdiction_from_ip, extract_client_ip
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from solicitor_directory import DISCLAIMER as SOLICITOR_DISCLAIMER  # noqa: E402
from solicitor_directory import get_solicitors  # noqa: E402

from content_extractor import ContentExtractor
from conversation_log import log_conversation
from email_receipt import send_receipt
from models import (
    ALLOWED_IMAGE_MIMES,
    AnalyzeContentRequest,
    AnalyzeContentResponse,
    ContentType,
    ExtractedContent,
    GenerateReportRequest,
    GenerateReportResponse,
    HealthResponse,
    ImageQueryRequest,
    QueryRequest,
    QueryResponse,
    StatsResponse,
    SubmitReportRequest,
    SubmitReportResponse,
)
from rag_service import RAGService
from report_generator import get_report_prompt, parse_report_sections

# Load environment variables (override system env vars with .env file values)
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- API Configuration ---
API_TITLE = "Project Ad'l (عادل) — RAG API"
API_DESCRIPTION = """
# UK Discrimination Law Knowledge Base API

**"Educate First, Litigate Second"** — A Muslim Council of Britain Initiative

Project Ad'l is a legal-tech platform tailored to the British Muslim experience,
grounded in the **British Muslim Manifesto: Vision 2050**. This API provides
AI-powered legal guidance using Retrieval-Augmented Generation (RAG) with
Google Gemini and a curated UK legal knowledge base.

---

## 📚 Grounding Sources

### England, Wales & Scotland (UK-wide)
| Source | Coverage |
|--------|----------|
| **Equality Act 2010** | Direct & indirect discrimination, harassment, victimisation (ss.13–27) |
| **Public Order Act 1986** | Racial & religious hatred offences — England & Wales only (Part 3A) |
| **Online Safety Act 2023** | Platform duties, illegal content, priority offences |
| **Crime and Disorder Act 1998** | Religiously aggravated offences (ss.28–32) |
| **Human Rights Act 1998** | Article 9 (freedom of religion), Article 14 (non-discrimination) |
| **UK Case Law** | 9 landmark cases including *Eweida v UK*, *Vento v Chief Constable* |
| **Vento Guidelines 2025/26** | Injury to feelings compensation bands |

### 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland-specific
| Source | Coverage |
|--------|----------|
| **Hate Crime and Public Order (Scotland) Act 2021** | Aggravation by prejudice (Part 1), stirring up hatred offences (Part 3) |

### 🇬🇧 Northern Ireland-specific
| Source | Coverage |
|--------|----------|
| **Fair Employment and Treatment (NI) Order 1998** | Religious belief & political opinion discrimination in employment |
| **Race Relations (NI) Order 1997** | Race discrimination in employment, goods & services |
| **Disability Discrimination Act 1995** | Disability discrimination (still live in NI) |

## ⚖️ The Pedagogical Funnel

All responses follow a mandatory **Educate → Resolve → Litigate** workflow:

1. **Intake** — Clarifying questions (jurisdiction, timeline, steps taken)
2. **Triage** — Match against Equality Act 2010 triggers → "Know Your Rights" guidance
3. **Actionable Next Steps** — 3-5 relevant organisations (Tell MAMA, ACAS, Law Society, etc.)
4. **Escalation** — Evidence strength evaluation (*Ilm* Threshold) → solicitor referral

> ⚠️ **FR1 Compliance:** The system will NEVER recommend litigation as the first step.

## 📞 Actionable Next Steps

Every post-intake response includes a **"What You Can Do Now"** section with 3-5 relevant
organisations selected by topic, jurisdiction, and severity — including Tell MAMA, IRU,
True Vision, Stop Hate UK, EASS, ACAS, Citizens Advice, Law Society, and Employment Tribunal.

## 📸 Image Analysis

Upload screenshots or photos for multimodal legal analysis using Gemini 3 Flash:
- **Screenshots** — discriminatory messages, social media posts, workplace communications
- **Document photos** — letters, notices, legal documents
- Up to **5 images** per message (PNG, JPEG, GIF, WebP — max 10MB each)
- Optional text question alongside images for targeted analysis

## 🔗 Content Extraction

Supports automatic content extraction from:
- **YouTube** — transcripts (including Shorts and Live), with manual fallback
- **Facebook** — video metadata and subtitles via yt-dlp, OG meta fallback
- **Twitter/X** — tweet text via FXTwitter API, video subtitles via yt-dlp
- **Instagram** — OG meta scrape, yt-dlp fallback (with cookies)
- **Webpages** — full-text scraping with Content-Type validation

## 📋 Report Submission

Submit hate crime reports directly to external reporting portals via AI-powered browser automation:
- **Police UK** — National hate crime report (England & Wales)
- **Tell MAMA** — Anti-Muslim hate incidents (UK-wide)
- **Police Scotland** — Hate crime report (Scotland)
- **IRU** — Islamophobia Response Unit (UK-wide)
- **Islamophobia UK** — Anonymous incident tracker (UK-wide)
- **EASS** — Equality Advisory Support Service (email report)
- **Stop Hate UK** — 24/7 hate crime support (email report)

The system collects user consent, fills external forms using AI browser automation (browser-use + Gemini Flash),
and returns confirmation with reference numbers. PII is never stored — passed through and immediately discarded.
Email confirmations are sent via SendGrid from `noreply@mcbx.app`.

Endpoints:
- `POST /api/v1/submit-report` — Submit a report to a target organisation
- `GET /api/v1/report-targets` — List available reporting targets and required fields

## 🔐 Security

All protected endpoints require an `X-API-Key` header. Use the **Authorize** button
above to enter your API key for testing.

**Security features:**
- SSRF protection on all outbound URL fetching (rejects private IPs)
- Input validation with max_length constraints (query: 10K, content: 50K chars)
- Conversation history limited to 50 turns
- Prompt injection resistance in system prompt
- TLS certificate verification on all external requests
- Generic error messages (no internal details leaked to clients)

## 🚦 Rate Limiting

| Endpoint Type | Default Limit |
|---------------|---------------|
| Query / Analyze | 30 requests/minute |
| Health / Stats | 60 requests/minute |

Rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`)
are included in all responses.
"""
API_VERSION = "1.3.0"

# --- Security Configuration ---
API_KEY = os.getenv("ADIL_API_KEY")
api_key_header = APIKeyHeader(
    name="X-API-Key",
    description="API key for authentication. Required for all protected endpoints.",
    auto_error=False,
)

# --- Rate Limiting ---
RATE_LIMIT_QUERY = os.getenv("RATE_LIMIT_QUERY", "30/minute")
RATE_LIMIT_GENERAL = os.getenv("RATE_LIMIT_GENERAL", "60/minute")
limiter = Limiter(key_func=get_remote_address)

# --- CORS Configuration ---
DEFAULT_ORIGINS = [
    "https://askadil.org",
    "https://www.askadil.org",
    "https://adil-frontend-production.up.railway.app",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080",
]
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else DEFAULT_ORIGINS
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

# Global services and stats
rag_service: RAGService | None = None
content_extractor: ContentExtractor | None = None
_stats_lock = asyncio.Lock()
stats = {
    "total_queries": 0,
    "total_tokens": 0,
    "total_cost": 0.0,
    "viability_assessments": 0,
    "content_analyses": 0,
    "start_time": time.time(),
}


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validate the API key from the X-API-Key header.

    Raises:
        HTTPException 401: If no API key is provided.
        HTTPException 403: If the API key is invalid.

    Returns:
        The validated API key string.
    """
    if not API_KEY:
        # If no API key is configured, allow all requests (dev mode)
        logger.warning("ADIL_API_KEY not set — running in OPEN mode (no auth)")
        return "open"
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide it in the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not secrets.compare_digest(api_key, API_KEY):
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key.",
        )
    return api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global rag_service, content_extractor

    logger.info(f"Starting {API_TITLE}...")

    # Validate required environment variables
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    file_search_store_id = os.getenv("FILE_SEARCH_STORE_ID")

    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set. Get one at https://aistudio.google.com/apikey")
    if not file_search_store_id:
        raise ValueError("FILE_SEARCH_STORE_ID not set. Run document-uploader first to create a store.")

    # Warn if no API key is configured
    if not API_KEY:
        logger.warning("⚠️  ADIL_API_KEY not set — API is running WITHOUT authentication")
    else:
        logger.info("🔐 API key authentication enabled")

    # Initialize RAG service
    rag_service = RAGService(gemini_api_key, file_search_store_id)

    # Initialize content extractor (for URL and YouTube transcript processing)
    content_extractor = ContentExtractor()

    logger.info(f"🚦 Rate limits: query={RATE_LIMIT_QUERY}, general={RATE_LIMIT_GENERAL}")
    logger.info(f"🌐 CORS origins: {ALLOWED_ORIGINS}")
    logger.info("✅ Project Adil RAG API started successfully")
    yield
    logger.info("Project Adil RAG API shutdown complete")


# --- OpenAPI Tag Metadata ---
tags_metadata = [
    {
        "name": "Public",
        "description": "Public endpoints — no authentication required.",
    },
    {
        "name": "Health",
        "description": "Service health and readiness checks.",
    },
    {
        "name": "Query",
        "description": (
            "**Core legal query endpoints.** Submit a text question or upload images (screenshots, "
            "photos of documents) about UK discrimination law. Receive an AI-generated answer "
            "grounded in legislation, case law, and guidelines. Image analysis uses Gemini 3 Flash "
            "multimodal vision. Optionally request a litigation viability assessment with Vento band estimation."
        ),
    },
    {
        "name": "Content Analysis",
        "description": (
            "**URL & content analysis endpoint.** Submit URLs (YouTube, Facebook videos/reels, Twitter/X tweets, Instagram posts, news articles) "
            "or plain text describing an incident. The system extracts content (tweet text via FXTwitter, video subtitles via yt-dlp), "
            "analyses it against UK discrimination law, and returns legal guidance with platform-specific advice."
        ),
    },
    {
        "name": "Report Submission",
        "description": (
            "**Hate crime report submission endpoints.** Submit reports to external portals "
            "(Police UK, Tell MAMA, Police Scotland, IRU, Islamophobia UK) via AI-powered browser "
            "automation, or to EASS and Stop Hate UK via email. The system collects user consent, "
            "fills forms automatically, and returns confirmation with reference numbers. "
            "Email receipts sent via SendGrid. PII is never stored."
        ),
    },
    {
        "name": "Monitoring",
        "description": "Usage statistics and operational metrics. Requires authentication.",
    },
    {
        "name": "Analytics",
        "description": "Anonymised aggregate analytics from conversation logs. Requires authentication.",
    },
    {
        "name": "Solicitor Directory",
        "description": "Curated directory of solicitors with discrimination law expertise. Filterable by jurisdiction, specialism, and location.",
    },
]

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
    contact={
        "name": "Project Ad'l Technical Team",
        "url": "https://askadil.org",
    },
    license_info={
        "name": "Proprietary",
    },
    swagger_ui_parameters={
        "persistAuthorization": True,
        "docExpansion": "list",
        "filter": True,
        "tryItOutEnabled": True,
    },
)

# --- Middleware ---
# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restricted to known origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Accept"],
)


# Log validation errors so we can debug 422s
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# --- Request Timing Middleware ---
@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    logger.info(
        "request_completed path=%s method=%s status=%d duration_ms=%d",
        request.url.path,
        request.method,
        response.status_code,
        duration_ms,
    )
    return response


# --- Report Bridge Configuration ---
REPORT_BRIDGE_URL = os.getenv("REPORT_BRIDGE_URL")
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY")


# =============================================================================
# PUBLIC ENDPOINTS (no auth required)
# =============================================================================


@app.get("/", tags=["Public"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def root(request: Request):
    """
    **Service discovery endpoint.**

    Returns basic service information and links to documentation.
    No authentication required.
    """
    return {
        "service": API_TITLE,
        "version": API_VERSION,
        "description": "UK Discrimination Law Knowledge Base — Educate First, Litigate Second",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "authentication": "X-API-Key header required for /api/* and /stats endpoints",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def health_check(request: Request):
    """
    **Health check endpoint.**

    Returns the current health status of the API, including whether the
    Gemini LLM connection is active. Use this for load balancer health probes
    and service monitoring.

    No authentication required.

    **Status values:**
    - `healthy` — All systems operational
    - `degraded` — RAG service not initialised (Gemini connection failed)
    """
    return HealthResponse(
        status="healthy" if rag_service else "degraded", version=API_VERSION, gemini_connected=rag_service is not None
    )


@app.get("/api/v1/detect-jurisdiction", tags=["Public"])
@limiter.limit("30/minute")
async def detect_jurisdiction(request: Request):
    """Auto-detect user's UK jurisdiction from IP address.

    Uses IP geolocation to suggest England & Wales, Scotland, or Northern Ireland.
    No authentication required. Returns null if detection fails or user is outside UK.
    """
    client_ip = extract_client_ip(dict(request.headers)) or request.client.host
    jurisdiction = await detect_jurisdiction_from_ip(client_ip)
    return {
        "jurisdiction": jurisdiction,
        "source": "ip_geolocation",
        "confidence": "approximate",
        "message": (
            f"Based on your location, you appear to be in {jurisdiction}."
            if jurisdiction
            else "Could not detect your location. Please select your jurisdiction."
        ),
    }


# =============================================================================
# PROTECTED ENDPOINTS (API key required)
# =============================================================================


@app.get("/stats", response_model=StatsResponse, tags=["Monitoring"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def get_stats(request: Request, _api_key: str = Security(verify_api_key)):
    """
    **Usage statistics and operational metrics.**

    Returns cumulative usage data since the last service restart, including:
    - Total queries processed
    - Token consumption and estimated cost (USD)
    - Number of viability assessments requested
    - Service uptime

    🔐 **Requires `X-API-Key` header.**
    """
    async with _stats_lock:
        uptime = int(time.time() - stats["start_time"])
        avg_tokens = stats["total_tokens"] / max(stats["total_queries"], 1)

        return StatsResponse(
            total_queries=stats["total_queries"],
            total_tokens_used=stats["total_tokens"],
            total_cost_usd=round(stats["total_cost"], 4),
            average_tokens_per_query=round(avg_tokens, 2),
            uptime_seconds=uptime,
            viability_assessments_count=stats["viability_assessments"],
        )


@app.get("/api/v1/analytics", tags=["Analytics"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def analytics(request: Request, _api_key: str = Security(verify_api_key)):
    """Anonymised usage analytics from conversation logs.

    Returns aggregate statistics — no PII, no message content.
    """
    from conversation_log import get_analytics_summary

    summary = await get_analytics_summary()
    if summary is None:
        raise HTTPException(status_code=503, detail="Analytics database not configured.")
    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LITIGATION_KEYWORDS = ["tribunal", "sue", "claim", "compensation", "solicitor", "lawyer"]


def _check_litigation_mentioned(answer: str) -> bool:
    """Check if the AI response mentions litigation-related terms."""
    answer_lower = answer.lower()
    return any(kw in answer_lower for kw in _LITIGATION_KEYWORDS)


# Mapping from content_extractor platform strings to models.ContentType
_CONTENT_TYPE_MAP = {
    "youtube": ContentType.YOUTUBE,
    "twitter": ContentType.SOCIAL_MEDIA,
    "instagram": ContentType.SOCIAL_MEDIA,
    "facebook": ContentType.SOCIAL_MEDIA,
    "webpage": ContentType.URL,
    "text": ContentType.TEXT,
}


def _parse_suggested_questions(answer: str) -> list[str] | None:
    """Extract suggested follow-up questions from the AI answer text.

    The system prompt instructs the model to include a section like:
        **Suggested next steps:**
        1. First question?
        2. Second question?
        3. Third question?

    Returns a list of question strings, or None if none found.
    """
    # Look for the "Suggested next steps" section
    pattern = r"\*{0,2}Suggested next steps:?\*{0,2}\s*\n((?:\s*\d+\.\s+.+\n?)+)"
    match = re.search(pattern, answer, re.IGNORECASE)
    if not match:
        return None

    block = match.group(1)
    questions = re.findall(r"\d+\.\s+(.+)", block)
    # Clean up: strip whitespace and trailing markdown
    questions = [q.strip().rstrip("*").strip() for q in questions if q.strip()]
    return questions if questions else None


@app.post(
    "/api/v1/query",
    response_model=QueryResponse,
    tags=["Query"],
    summary="Query UK discrimination law",
    responses={
        200: {"description": "Successful legal analysis with sources and metadata"},
        401: {"description": "Missing API key"},
        403: {"description": "Invalid API key"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "RAG service not initialised"},
    },
)
@limiter.limit(RATE_LIMIT_QUERY)
async def query(request: Request, body: QueryRequest, _api_key: str = Security(verify_api_key)):
    """
    **Execute a RAG query against the UK legal knowledge base.**

    Submit a natural-language question about UK discrimination law. The system will:

    1. **Search** the Gemini File Search Tool (FST) knowledge base for relevant legislation,
       case law, and guidelines.
    2. **Generate** an AI answer grounded in retrieved sources, following the
       "Educate First, Litigate Second" mandate (FR1).
    3. **Extract** statutory citations (e.g., "Section 13 of the Equality Act 2010") and
       case law references (e.g., *Eweida v United Kingdom [2013] ECHR 37*).
    4. **Return** structured sources with links to legislation.gov.uk and
       caselaw.nationalarchives.gov.uk.

    **Optional:** Set `include_viability_score: true` to request a preliminary litigation
    viability assessment with Vento band estimation.

    🔐 **Requires `X-API-Key` header.**

    ### Example Request
    ```json
    {
        "query": "My employer refused to let me take time off for Eid. What are my rights?",
        "max_sources": 5,
        "include_viability_score": false
    }
    ```
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    try:
        # Convert conversation history to dicts for the RAG service
        history_dicts = None
        if body.conversation_history:
            history_dicts = [{"role": turn.role, "content": turn.content} for turn in body.conversation_history]

        answer, sources, usage, metadata, viability, evidence_checklist = await rag_service.query(
            query_text=body.query,
            max_sources=body.max_sources,
            include_viability=body.include_viability_score,
            conversation_history=history_dicts,
        )

        # Update stats
        async with _stats_lock:
            stats["total_queries"] += 1
            stats["total_tokens"] += usage.total_tokens
            stats["total_cost"] += usage.estimated_cost_usd or 0
            if body.include_viability_score:
                stats["viability_assessments"] += 1

        # Check if litigation was mentioned
        litigation_mentioned = _check_litigation_mentioned(answer)

        # Parse suggested follow-up questions from the answer
        suggested_questions = _parse_suggested_questions(answer)

        # Log anonymised metadata (fire-and-forget)
        asyncio.create_task(
            log_conversation(
                endpoint="query",
                query_text=body.query,
                conversation_history=history_dicts,
                viability_requested=body.include_viability_score,
                response_time_ms=metadata.processing_time_ms,
                model_used=metadata.model_used,
                token_count=usage.total_tokens,
            )
        )

        return QueryResponse(
            answer=answer,
            sources=sources,
            viability=viability,
            usage=usage,
            query_metadata=metadata,
            educational_content_provided=True,
            litigation_mentioned=litigation_mentioned,
            suggested_questions=suggested_questions,
            evidence_checklist=evidence_checklist or None,
        )

    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again later.") from e


@app.post(
    "/api/v1/analyze",
    response_model=AnalyzeContentResponse,
    tags=["Content Analysis"],
    summary="Analyze URLs or text for legal issues",
    responses={
        200: {"description": "Successful content analysis with legal guidance"},
        401: {"description": "Missing API key"},
        403: {"description": "Invalid API key"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "RAG service or content extractor not initialised"},
    },
)
@limiter.limit(RATE_LIMIT_QUERY)
async def analyze_content(request: Request, body: AnalyzeContentRequest, _api_key: str = Security(verify_api_key)):
    """
    **Analyze content from URLs, videos, or text for potential legal issues.**

    Submit a URL or plain text describing an incident. The system will:

    1. **Detect URLs** in the content (YouTube, Twitter/X, Instagram, Facebook, news articles, any webpage).
    2. **Extract content** — scrape web pages, fetch YouTube transcripts, or retrieve
       social media post content.
    3. **Analyse** the extracted content against UK discrimination law using RAG.
    4. **Return** legal guidance with platform-specific advice (e.g., how to report
       under the Online Safety Act 2023).

    **Supported platforms:**
    - 📺 **YouTube** — automatic transcript extraction
    - 📱 **Twitter/X** — full tweet text via FXTwitter API (video subtitles via yt-dlp)
    - 📸 **Instagram** — post caption via OG meta scrape (video metadata via yt-dlp with cookies)
    - 📘 **Facebook** — video metadata, subtitles & description via yt-dlp (with OG meta fallback)
    - 📰 **News articles** — full-text web scraping
    - 📝 **Plain text** — direct incident descriptions

    🔐 **Requires `X-API-Key` header.**

    ### Example Request (URL)
    ```json
    {
        "content": "https://www.youtube.com/watch?v=example — is this hate speech?",
        "include_viability_score": false
    }
    ```

    ### Example Request (Plain Text)
    ```json
    {
        "content": "A colleague posted Islamophobic comments on the company Slack channel targeting me during Ramadan.",
        "content_type": "text",
        "include_viability_score": true
    }
    ```
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")
    if not content_extractor:
        raise HTTPException(status_code=503, detail="Content extractor not initialized")

    try:
        # Process the content - extract URLs and their content
        processed = await content_extractor.process_message(body.content)

        # Use combined text (original + extracted content) for analysis
        analysis_text = processed.combined_text

        # Build context for the RAG query
        context_prefix = ""
        extracted_info = None
        platform = None

        if processed.url_count > 0:
            # Include extraction context
            successful_extractions = [e for e in processed.extracted_urls if e.success]
            if successful_extractions:
                first_extract = successful_extractions[0]
                platform = first_extract.content_type.value
                extracted_info = ExtractedContent(
                    content_type=_CONTENT_TYPE_MAP.get(platform, ContentType.TEXT),
                    source_url=first_extract.url,
                    raw_text=first_extract.text[:500] + "..." if len(first_extract.text) > 500 else first_extract.text,
                    title=first_extract.title,
                    platform=platform,
                    extraction_method=first_extract.metadata.get("source", "unknown"),
                    confidence=0.9 if first_extract.success else 0.5,
                )
                context_prefix = f"[Analyzing content from {platform}] "

        # Convert conversation history to dicts for the RAG service
        history_dicts = None
        if body.conversation_history:
            history_dicts = [{"role": turn.role, "content": turn.content} for turn in body.conversation_history]

        # Execute RAG query with the combined content
        answer, sources, usage, metadata, viability, evidence_checklist = await rag_service.query(
            query_text=context_prefix + analysis_text,
            max_sources=10,
            include_viability=body.include_viability_score,
            conversation_history=history_dicts,
        )

        # Update stats
        async with _stats_lock:
            stats["total_queries"] += 1
            stats["content_analyses"] += 1
            stats["total_tokens"] += usage.total_tokens
            stats["total_cost"] += usage.estimated_cost_usd or 0
            if body.include_viability_score:
                stats["viability_assessments"] += 1

        # Generate platform-specific advice
        platform_advice = None
        if platform == "twitter":
            platform_advice = (
                "📱 **Twitter/X Reporting:** If this content violates platform policies, "
                "you can report it via Twitter's 'Report Tweet' feature. For content that may "
                "violate the Online Safety Act 2023, document the post (screenshot with timestamp) "
                "before reporting, as it may be removed."
            )
        elif platform == "youtube":
            platform_advice = (
                "📺 **YouTube Reporting:** Hateful content can be reported via YouTube's "
                "'Report' button. Under the Online Safety Act 2023, platforms have duties "
                "to remove illegal content. Keep a record of the video URL and transcript."
            )
        elif platform == "instagram":
            platform_advice = (
                "📸 **Instagram Reporting:** Hateful or abusive content can be reported "
                "via Instagram's 'Report' option (tap the three dots on a post or comment). "
                "Under the Online Safety Act 2023, Meta must remove illegal content. "
                "Screenshot the post with timestamps before reporting, as it may be deleted."
            )
        elif platform == "facebook":
            platform_advice = (
                "📘 **Facebook Reporting:** Hateful or discriminatory content can be reported "
                "via Facebook's 'Report post' option (click the three dots on any post). "
                "Under the Online Safety Act 2023, Meta must remove illegal content. "
                "Screenshot the post with timestamps before reporting, as it may be deleted."
            )

        # Check if litigation was mentioned
        litigation_mentioned = _check_litigation_mentioned(answer)

        # Parse suggested follow-up questions from the answer
        suggested_questions = _parse_suggested_questions(answer)

        # Generate content summary if we extracted content
        content_summary = None
        if processed.url_count > 0:
            content_summary = f"Analyzed {processed.url_count} URL(s)."

        # Log anonymised metadata (fire-and-forget)
        asyncio.create_task(
            log_conversation(
                endpoint="analyze",
                query_text=body.content,
                conversation_history=history_dicts,
                has_urls=processed.url_count > 0,
                viability_requested=body.include_viability_score,
                response_time_ms=metadata.processing_time_ms,
                model_used=metadata.model_used,
                token_count=usage.total_tokens,
            )
        )

        return AnalyzeContentResponse(
            answer=answer,
            sources=sources,
            viability=viability,
            usage=usage,
            query_metadata=metadata,
            educational_content_provided=True,
            litigation_mentioned=litigation_mentioned,
            suggested_questions=suggested_questions,
            evidence_checklist=evidence_checklist or None,
            extracted_content=extracted_info,
            content_summary=content_summary,
            platform_specific_advice=platform_advice,
        )

    except Exception as e:
        logger.error(f"Content analysis error: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again later.") from e


@app.post(
    "/api/v1/query/image",
    response_model=QueryResponse,
    tags=["Query"],
    summary="Analyse images for legal issues",
    responses={
        200: {"description": "Successful image analysis with legal guidance"},
        400: {"description": "Invalid image data or unsupported format"},
        401: {"description": "Missing API key"},
        403: {"description": "Invalid API key"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "RAG service not initialised"},
    },
)
@limiter.limit(RATE_LIMIT_QUERY)
async def query_image(
    request: Request,
    body: ImageQueryRequest,
    _api_key: str = Security(verify_api_key),
):
    """
    **Analyse uploaded images for potential UK discrimination law issues.**

    Submit one or more images (screenshots of messages, photos of letters,
    evidence of discrimination) with an optional text question. The system uses
    Gemini 3 Flash multimodal vision to:

    1. **Understand** the image content (text, context, visual evidence).
    2. **Analyse** against UK discrimination law using the legal knowledge base.
    3. **Return** structured legal guidance with statutory citations and sources.

    **Supported formats:** PNG, JPEG, GIF, WebP (max 10MB each, max 5 images).

    🔐 **Requires `X-API-Key` header.**
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialized")

    # Validate image MIME types and base64 data
    for i, img in enumerate(body.images):
        if img.mime_type not in ALLOWED_IMAGE_MIMES:
            raise HTTPException(
                status_code=400,
                detail=f"Image {i + 1}: unsupported format '{img.mime_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_MIMES))}",
            )
        try:
            base64.b64decode(img.data, validate=True)
        except binascii.Error as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Image {i + 1}: invalid base64 data.",
            ) from exc

    try:
        # Convert conversation history
        history_dicts = None
        if body.conversation_history:
            history_dicts = [{"role": turn.role, "content": turn.content} for turn in body.conversation_history]

        # Convert images to dicts for the RAG service
        images_data = [{"mime_type": img.mime_type, "data": img.data} for img in body.images]

        answer, sources, usage, metadata, viability, evidence_checklist = await rag_service.query_with_images(
            images=images_data,
            query_text=body.query,
            max_sources=10,
            include_viability=body.include_viability_score,
            conversation_history=history_dicts,
        )

        # Update stats
        async with _stats_lock:
            stats["total_queries"] += 1
            stats["total_tokens"] += usage.total_tokens
            stats["total_cost"] += usage.estimated_cost_usd or 0
            if body.include_viability_score:
                stats["viability_assessments"] += 1

        litigation_mentioned = _check_litigation_mentioned(answer)
        suggested_questions = _parse_suggested_questions(answer)

        return QueryResponse(
            answer=answer,
            sources=sources,
            viability=viability,
            usage=usage,
            query_metadata=metadata,
            educational_content_provided=True,
            litigation_mentioned=litigation_mentioned,
            suggested_questions=suggested_questions,
            evidence_checklist=evidence_checklist or None,
        )

    except Exception as e:
        logger.error(f"Image query error: {e}")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred. Please try again later.",
        ) from e


@app.get("/api/v1/privacy-notice", tags=["Public"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def privacy_notice(request: Request):
    """
    **Privacy notice for AskAdil.**

    Returns the privacy notice as structured JSON so consuming services can
    display it to users before collecting PII or submitting reports.
    No authentication required.
    """
    return {
        "version": "2026-03-24",
        "summary": "AskAdil does not store conversations or personal information. PII collected for report submission is passed through to the target organisation and immediately discarded.",
        "data_handling": {
            "conversations": "Exist in browser session only. Not stored on servers.",
            "pii_for_reports": "Passed through to target organisation. Immediately discarded after submission. Never written to disk, database, or logs.",
            "anonymised_analytics": "Topic category, jurisdiction, and usage metadata logged to Postgres. Cannot identify individuals.",
            "email_receipts": "Sent via SendGrid from noreply@mcbx.app. AskAdil does not store sent emails.",
        },
        "lawful_basis": {
            "conversations": "Legitimate interest (UK GDPR Art 6.1.f)",
            "report_submission": "Explicit consent (UK GDPR Art 6.1.a)",
            "special_category": "Explicit consent (UK GDPR Art 9.2.a) + Substantial public interest (Art 9.2.g)",
            "analytics": "Legitimate interest (UK GDPR Art 6.1.f)",
        },
        "user_rights": [
            "Access — AskAdil stores no personal data to access",
            "Erasure — No personal data stored to erase",
            "Withdraw consent — Cancel report at any time before submission",
            "Complain — Contact ICO at ico.org.uk",
        ],
        "third_parties": [
            {
                "name": "Target organisation (e.g. Police UK, Tell MAMA)",
                "receives": "Reporter PII + incident details (only on report submission with consent)",
            },
            {"name": "Google Gemini", "receives": "Anonymised conversation messages for AI processing"},
            {"name": "Railway (hosting)", "receives": "Technical data (IP, request logs). No message content."},
            {"name": "SendGrid", "receives": "User email address for confirmation receipts only"},
        ],
        "full_notice_url": "https://askadil.org/privacy",
    }


# =============================================================================
# REPORT SUBMISSION ENDPOINTS
# =============================================================================


@app.get("/api/v1/report-targets", tags=["Report Submission"])
@limiter.limit(RATE_LIMIT_GENERAL)
async def report_targets(request: Request, _api_key: str = Security(verify_api_key)):
    """
    **Available reporting targets with required fields.**

    Returns all configured reporting targets so consuming services know
    what PII to collect before calling `/api/v1/submit-report`.
    Each target includes a `pii_required` flag — if `false`, the target
    accepts anonymous reports (no personal details needed).

    🔐 **Requires `X-API-Key` header.**
    """
    if not REPORT_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="Report bridge not configured.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{REPORT_BRIDGE_URL}/targets",
                headers={"X-Bridge-Key": BRIDGE_API_KEY or ""},
            )
            resp.raise_for_status()
            targets = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch report targets: {e}")
            raise HTTPException(status_code=503, detail="Report bridge unavailable.") from e

    # Enhance with pii_required flag for consuming services
    NO_PII_TARGETS = {"islamophobia-uk"}
    for tid, tdata in targets.items():
        tdata["pii_required"] = tid not in NO_PII_TARGETS

    return targets


@app.post(
    "/api/v1/submit-report",
    response_model=SubmitReportResponse,
    tags=["Report Submission"],
    summary="Submit a hate crime report via automated form filling",
)
@limiter.limit(RATE_LIMIT_QUERY)
async def submit_report(
    request: Request,
    body: SubmitReportRequest,
    _api_key: str = Security(verify_api_key),
):
    """Submit a hate crime report to an external reporting portal.

    The bridge service fills and submits the form using AI browser automation.
    If submission fails, a fallback report is generated for manual submission.

    WARNING: This endpoint handles PII. Data is passed through to the bridge
    and never persisted. Do NOT retry on failure.
    """
    if not REPORT_BRIDGE_URL:
        raise HTTPException(status_code=503, detail="Report bridge not configured.")

    if not body.consent_confirmed:
        raise HTTPException(
            status_code=400,
            detail="consent_confirmed must be true. The user must explicitly consent before report submission.",
        )

    # Transform nested public format → flat bridge format
    bridge_data = {
        "first_name": body.reporter.first_name,
        "surname": body.reporter.surname,
        "dob": body.reporter.dob,
        "gender": body.reporter.gender,
        "email": body.reporter.email,
        "phone": body.reporter.phone,
        "address": body.reporter.address,
        "role": body.incident.role,
        "incident_details": body.incident.details,
        "location": body.incident.location,
        "date_time": body.incident.date_time,
        "suspect_description": body.incident.suspect_description,
        "evidence_urls": body.evidence_urls or [],
        "additional_info": "Submitted via AskAdil (askadil.org) on behalf of the reporter.",
    }

    # Remove None values
    bridge_data = {k: v for k, v in bridge_data.items() if v is not None}

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{REPORT_BRIDGE_URL}/submit",
                headers={"X-Bridge-Key": BRIDGE_API_KEY or ""},
                json={"target": body.target, "data": bridge_data},
            )
            resp.raise_for_status()
            result = resp.json()
    except httpx.TimeoutException:
        logger.error("Bridge timeout for target=%s", body.target)
        result = {"success": False}
    except Exception as e:
        logger.error("Bridge call failed for target=%s: %s", body.target, e)
        result = {"success": False}

    del bridge_data

    # Log anonymised report submission metadata (fire-and-forget)
    asyncio.create_task(
        log_conversation(
            endpoint="submit_report",
            query_text="",
            report_submitted=True,
            report_target=body.target,
            report_success=result.get("success", False),
        )
    )

    if result.get("success"):
        ref = result.get("reference_number", "N/A")
        target_display = body.target.replace("-", " ").title()

        # Send email receipt to user (fire-and-forget, never blocks response)
        if body.reporter.email and body.reporter.email != "anonymous@askadil.org":
            asyncio.create_task(
                send_receipt(
                    to_email=body.reporter.email,
                    target_name=target_display,
                    reference_number=result.get("reference_number"),
                    incident_summary=body.incident.details[:300],
                    submitted_at=result.get("submitted_at"),
                )
            )

        return SubmitReportResponse(
            success=True,
            target=body.target,
            reference_number=result.get("reference_number"),
            confirmation_screenshot=result.get("confirmation_screenshot"),
            message=(
                f"Your hate crime report has been submitted to "
                f"{target_display}. "
                f"Please save reference number {ref}. "
                f"A confirmation email has been sent to {body.reporter.email}."
            ),
            submitted_at=result.get("submitted_at"),
        )
    else:
        fallback = None
        if rag_service and body.conversation_history:
            try:
                history_dicts = [{"role": t.role, "content": t.content} for t in body.conversation_history]
                fallback_answer, _, _, _, _, _ = await rag_service.query(
                    query_text=(
                        "INSTRUCTION: You are generating a structured incident report, NOT having a conversation. "
                        "Do NOT ask questions. Do NOT request more information. "
                        "Use ONLY the information available in the conversation history below. "
                        "If a detail is missing, write 'Not provided' for that section.\n\n"
                        "Generate the report in this exact format:\n\n"
                        "--- INCIDENT REPORT SUMMARY ---\n"
                        "Generated by AskAdil\n\n"
                        "WHAT HAPPENED:\n[Summarise the incident from the conversation]\n\n"
                        "WHERE THIS HAPPENED:\n[Location if mentioned, otherwise 'Not provided']\n\n"
                        "WHEN THIS HAPPENED:\n[Date/time if mentioned, otherwise 'Not provided']\n\n"
                        "SUSPECT DESCRIPTION:\n[If mentioned, otherwise 'Not provided']\n\n"
                        "LEGAL CONTEXT:\n[Relevant legislation identified during the conversation]\n\n"
                        "--- END REPORT ---"
                    ),
                    max_sources=0,
                    include_viability=False,
                    conversation_history=history_dicts,
                )
                fallback = fallback_answer
            except Exception as e:
                logger.error(f"Fallback report generation failed: {e}")

        return SubmitReportResponse(
            success=False,
            target=body.target,
            error=result.get("error", "Automated submission failed. Please submit manually using the report below."),
            fallback_report=fallback,
            target_url=result.get("target_url"),
        )


# =============================================================================
# REPORT GENERATION ENDPOINTS
# =============================================================================


@app.post(
    "/api/v1/generate-report",
    response_model=GenerateReportResponse,
    tags=["Report Generation"],
    summary="Generate a structured incident report or solicitor consultation pack",
)
@limiter.limit(RATE_LIMIT_QUERY)
async def generate_report(
    request: Request,
    body: GenerateReportRequest,
    _api_key: str = Security(verify_api_key),
):
    """Generate a structured report from conversation history.

    Two report types:
    - **incident_summary**: For self-service hate crime reporting. Generates
      a structured summary the user can copy-paste into Police, Tell MAMA, or IRU forms.
    - **solicitor_pack**: For solicitor-path cases. Generates a consultation
      preparation pack with key dates, legislation, and questions to ask.

    Requires `X-API-Key` header.
    """
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG service not initialised.")

    prompt = get_report_prompt(body.report_type.value, body.jurisdiction)

    history_dicts = [{"role": t.role, "content": t.content} for t in body.conversation_history]

    try:
        answer, _, usage, metadata, _, _ = await rag_service.query(
            query_text=prompt,
            max_sources=0,
            include_viability=False,
            conversation_history=history_dicts,
        )
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate report. Please try again.",
        ) from e

    sections = parse_report_sections(answer)

    # Log anonymised metadata (fire-and-forget)
    asyncio.create_task(
        log_conversation(
            endpoint="generate_report",
            query_text="",
            conversation_history=history_dicts,
        )
    )

    return GenerateReportResponse(
        report_text=answer,
        report_type=body.report_type,
        sections=sections,
        jurisdiction=body.jurisdiction,
    )


# =============================================================================
# SOLICITOR DIRECTORY ENDPOINT
# =============================================================================


@app.get(
    "/api/v1/solicitors",
    tags=["Solicitor Directory"],
    summary="Browse curated solicitor directory",
    responses={
        200: {"description": "List of solicitors matching filters"},
        401: {"description": "Missing API key"},
        403: {"description": "Invalid API key"},
    },
)
@limiter.limit(RATE_LIMIT_GENERAL)
async def list_solicitors(
    request: Request,
    jurisdiction: str | None = None,
    specialism: str | None = None,
    location: str | None = None,
    _api_key: str = Security(verify_api_key),
):
    """
    **Browse the curated solicitor directory.**

    Returns a list of solicitors with discrimination law expertise,
    sourced from publicly available information. All firms are pending
    outreach — none have consented to be listed yet.

    **Filters (all optional):**
    - `jurisdiction` — e.g. "scotland", "england", "northern ireland"
    - `specialism` — e.g. "employment", "discrimination", "hate_crime"
    - `location` — e.g. "london", "birmingham", "glasgow"

    All filters are case-insensitive partial matches.

    🔐 **Requires `X-API-Key` header.**
    """
    results = get_solicitors(
        jurisdiction=jurisdiction,
        specialism=specialism,
        location=location,
    )
    return {
        "solicitors": results,
        "total": len(results),
        "disclaimer": SOLICITOR_DISCLAIMER,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
