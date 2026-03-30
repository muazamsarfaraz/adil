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

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
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
