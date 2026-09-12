"""Stable per-document anchor allocation."""

from __future__ import annotations


class AnchorAllocator:
    """Allocate sequential ids independently for each supported IR kind."""

    _prefixes = {"sec", "eq", "fig", "tab", "bib", "fn", "para"}

    def __init__(self) -> None:
        self._counts = dict.fromkeys(self._prefixes, 0)

    def next(self, kind: str) -> str:
        if kind not in self._prefixes:
            raise ValueError(f"unknown anchor kind: {kind}")
        self._counts[kind] += 1
        return f"{kind}-{self._counts[kind]}"
