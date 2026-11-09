from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

# The shell is static and holds no data; every data call the page makes carries the API key.
# 'self' only: no inline script or style, no third-party origins, so text from a failing service
# (error messages, step names) cannot become executable.
_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

router = APIRouter(prefix="/ui", include_in_schema=False)


@router.get("")
@router.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Content-Security-Policy": _CSP,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
