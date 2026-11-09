import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import api_key

# Read at import time so a missing secret fails the process at boot, never serves unauthenticated.
_EXPECTED_KEY = api_key()
_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided: str | None = Security(_header)) -> None:
    if provided is None or not secrets.compare_digest(provided, _EXPECTED_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")
