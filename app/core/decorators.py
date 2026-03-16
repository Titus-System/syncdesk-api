from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from pydantic import BaseModel

P = ParamSpec("P")
R = TypeVar("R")


def require_dto(
    *dto_types: type[BaseModel],
) -> Callable[
    [Callable[P, Awaitable[R]]],
    Callable[P, Awaitable[R]],
]:
    if not dto_types:
        raise ValueError("At least one DTO type must be provided")

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            dto = kwargs.get("data") or kwargs.get("dto") or args[-1]
            if not isinstance(dto, dto_types):
                expected = ", ".join(t.__name__ for t in dto_types)
                raise TypeError(f"Expected one of ({expected}), got {type(dto).__name__}")
            return await fn(*args, **kwargs)

        return wrapper

    return decorator
