from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.rate_limit import limiter
from app.api.campaigns import router as campaigns_router
from app.api.contacts import router as contacts_router
from app.api.dashboard import router as dashboard_router
from app.api.outreach import router as outreach_router
from app.api.public import public_router
from app.api.conversion_webhooks import conversion_webhooks_router
from app.api.webhooks import router as webhooks_router

tags_metadata = [
    {
        "name": "campaigns",
        "description": "Campaign CRUD operations: create, list, update, delete, launch, and pause outreach campaigns.",
    },
    {
        "name": "contacts",
        "description": "Contact management: add, list, update, delete, and bulk-import contacts within a campaign.",
    },
    {
        "name": "outreach",
        "description": "Outreach pipeline triggers: research, draft, approve, and send emails for individual contacts.",
    },
    {
        "name": "webhooks",
        "description": "Inbound webhook handlers for SendGrid (email events), Stripe (payment events), and Cal.com (booking events).",
    },
    {
        "name": "public",
        "description": "Public conversion pages: branded signup, booking, and payment pages accessible without authentication.",
    },
    {
        "name": "dashboard",
        "description": "Campaign analytics: funnel metrics, conversion stats, and CSV data export.",
    },
]

app = FastAPI(
    title="AskAdil Outreach Engine API",
    description=(
        "AI-powered outreach and conversion platform for AskAdil by MCB. "
        "Manages multi-step email campaigns with LLM-driven research, "
        "personalised drafting, reply classification, and conversion tracking.\n\n"
        "## Endpoint Groups\n\n"
        "- **Campaigns** -- CRUD operations for outreach campaigns with launch/pause controls\n"
        "- **Contacts** -- Contact management with bulk import and status tracking\n"
        "- **Outreach** -- Pipeline step triggers (research, draft, approve, send) per contact\n"
        "- **Webhooks** -- Inbound event processing from SendGrid, Stripe, and Cal.com\n"
        "- **Public** -- Branded conversion pages (signup, booking, payment) per campaign\n"
        "- **Dashboard** -- Funnel metrics, conversion analytics, and CSV export\n\n"
        "## Authentication\n\n"
        "All authenticated endpoints require an `X-API-Key` header. "
        "Public and webhook endpoints are accessible without authentication."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
    contact={
        "name": "AskAdil Team",
        "url": "https://askadil.org",
    },
    license_info={
        "name": "Proprietary",
    },
)

app.state.limiter = limiter


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
        headers={"Retry-After": "60"},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Authenticated routers
app.include_router(campaigns_router)
app.include_router(contacts_router)
app.include_router(dashboard_router)
app.include_router(outreach_router)

# Public routers (rate-limited, no auth)
app.include_router(public_router)

# Webhook routers (no auth, no rate limit — trusted services)
app.include_router(conversion_webhooks_router)
app.include_router(webhooks_router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
