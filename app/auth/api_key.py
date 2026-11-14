import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import api_key

# Read at import time so a missing secret fails the process at boot, never serves unauthenticated.
_EXPECTED_KEY = api_key()
_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided: str | None = Security(_header)) -> None:
    if provided is None or not secrets.compare_digest(provided, _EXPECTED_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_api_key_for_writes(request: Request, provided: str | None = Security(_header)) -> None:
    """Read-only requests are open (the web UI browses without a key); anything that changes data needs it."""
    if request.method not in _SAFE_METHODS:
        require_api_key(provided)
