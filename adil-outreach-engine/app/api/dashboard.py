from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/api/v1/outreach", tags=["dashboard"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    checks = {}

    # Check PostgreSQL
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"

    overall_status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall_status,
        "version": settings.app_version,
        "service": settings.app_name,
        "checks": checks,
    }
