from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

STATIC_DIR = Path(__file__).parent / "static"

# The shell is static and holds no data. Reads are open; the page sends the API key only for write actions.
# 'self' only: no inline script or style, no third-party origins, so text from a failing service
# (error messages, step names) cannot become executable.
_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

router = APIRouter(include_in_schema=False)


@router.get("/ui")
@router.get("/ui/")
def legacy_path() -> RedirectResponse:
    return RedirectResponse("/", status_code=308)


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
