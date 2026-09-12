"""Schema registry for the paperdeck LLM protocol."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel

from .models import PdfBibV1, PdfCiteMapV1, PdfEquationLatexV1, PdfSegmentV1

SchemaModel: TypeAlias = type[BaseModel]
_REGISTRY: dict[str, tuple[SchemaModel, str]] = {
    "pdf_segment": (PdfSegmentV1, "v1"),
    "pdf_segment.v1": (PdfSegmentV1, "v1"),
    "pdf_equation_latex": (PdfEquationLatexV1, "v1"),
    "pdf_equation_latex.v1": (PdfEquationLatexV1, "v1"),
    "pdf_bib": (PdfBibV1, "v1"),
    "pdf_bib.v1": (PdfBibV1, "v1"),
    "pdf_cite_map": (PdfCiteMapV1, "v1"),
    "pdf_cite_map.v1": (PdfCiteMapV1, "v1"),
}


def get(name: str) -> tuple[SchemaModel, str]:
    """Return the model and wire version for a schema name."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown LLM schema: {name}") from exc


__all__ = [
    "PdfBibV1",
    "PdfCiteMapV1",
    "PdfEquationLatexV1",
    "PdfSegmentV1",
    "get",
]
