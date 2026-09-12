"""Input resolver contracts, implemented by the input issues."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputSpec:
    """Minimal input descriptor shared by conversion engines."""

    original: str
