"""Shared schema base classes."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base DTO: camelCase on the wire, snake_case in Python, ORM-friendly.

    - ``alias_generator=to_camel``: JSON uses camelCase (frontend contract).
    - ``populate_by_name=True``: constructing from Python may use snake_case.
    - ``from_attributes=True``: models validate straight off ORM objects.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class Page(CamelModel, Generic[T]):
    """Generic offset-paginated result."""

    items: list[T]
    total: int
