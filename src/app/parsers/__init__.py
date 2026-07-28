from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import FeedItem, SourceConfig

# Registry: maps parser_id from sources.yml to a parse function.
# Each function signature: (html: str, source: SourceConfig) -> list[FeedItem]
PARSERS: dict[str, Callable[[str, SourceConfig], list[FeedItem]]] = {}


def register(parser_id: str):
    """Decorator to register a parser function."""

    def wrapper(fn: Callable[[str, SourceConfig], list[FeedItem]]):
        PARSERS[parser_id] = fn
        return fn

    return wrapper


def get_parser(parser_id: str) -> Callable[[str, SourceConfig], list[FeedItem]]:
    if parser_id not in PARSERS:
        available = ", ".join(sorted(PARSERS.keys()))
        raise KeyError(f"Unknown parser '{parser_id}'. Available: {available}")
    return PARSERS[parser_id]
