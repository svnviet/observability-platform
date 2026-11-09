from typing import TypeVar

from fastapi import HTTPException

T = TypeVar("T")


def or_404(value: T | None, what: str) -> T:
    if value is None:
        raise HTTPException(404, f"{what} not found")
    return value
