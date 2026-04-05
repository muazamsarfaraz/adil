from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-Admin-Key")


async def require_admin_key(key: str = Security(_api_key_header)) -> str:
    if key != get_settings().admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return key
