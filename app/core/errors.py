from typing import TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def or_404(value: T | None, what: str) -> T:
    if value is None:
        raise HTTPException(404, f"{what} not found")
    return value


class Conflict(Exception):
    """The request is valid but the current state forbids it (HTTP 409)."""


def conflict_409(exc: Conflict) -> HTTPException:
    return HTTPException(409, str(exc))
