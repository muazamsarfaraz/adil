from fastapi import FastAPI

from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
