from fastapi import APIRouter, Depends

from app.auth.api_key import require_api_key

router = APIRouter(prefix="/auth", tags=["auth"], include_in_schema=False)


@router.get("/check", dependencies=[Depends(require_api_key)])
def check_key() -> dict[str, bool]:
    """Lets the UI verify a key before it offers write actions."""
    return {"ok": True}
