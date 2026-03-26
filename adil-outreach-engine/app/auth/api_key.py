from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# Alias for convenience
verify_api_key = require_api_key
