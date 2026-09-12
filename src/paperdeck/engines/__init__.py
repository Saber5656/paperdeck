"""Engine protocol and shared conversion context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

if TYPE_CHECKING:
    from paperdeck.config import Settings
    from paperdeck.ir.model import Document

    from ..input.cache import CacheManager
    from ..input.resolver import InputSpec
    from ..llm.cost import CostEstimate


@dataclass(frozen=True)
class EngineContext:
    spec: InputSpec
    settings: Settings
    cache: CacheManager
    workdir: Path
    confirm_cost: Callable[[CostEstimate], bool]
    run_metrics: dict[str, Any] = field(default_factory=dict)


class Engine(Protocol):
    name: ClassVar[str]

    def available(self, ctx: EngineContext) -> tuple[bool, str]: ...

    def convert(self, ctx: EngineContext) -> Document: ...
