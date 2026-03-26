from fastapi import FastAPI

from app.config import settings
from app.api.campaigns import router as campaigns_router
from app.api.contacts import router as contacts_router
from app.api.dashboard import router as dashboard_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(campaigns_router)
app.include_router(contacts_router)
app.include_router(dashboard_router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
