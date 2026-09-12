"""Versioned, bounded response models used at the LLM boundary."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Role = Literal[
    "title",
    "author_line",
    "abstract",
    "heading",
    "paragraph",
    "display_equation",
    "figure_caption",
    "table_caption",
    "table_body",
    "bib_entry",
    "noise",
]


class SegmentBlock(StrictModel):
    id: str = Field(max_length=40)
    role: Role
    level: int | None = Field(default=None, ge=1, le=4)
    number_text: str | None = Field(default=None, max_length=20)
    links_to_block: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def heading_level(self) -> SegmentBlock:
        if self.role == "heading" and self.level is None:
            raise ValueError("heading role requires level")
        if self.role != "heading" and self.level is not None:
            raise ValueError("level is only valid for heading")
        return self


class PdfSegmentV1(StrictModel):
    blocks: list[SegmentBlock] = Field(max_length=10000)
    section_order: list[str] = Field(max_length=10000)
    notes: str | None = Field(default=None, max_length=500)


class PdfEquationLatexV1(StrictModel):
    latex: str = Field(max_length=4000)
    confidence: float = Field(ge=0, le=1)


class BibEntryOutput(StrictModel):
    number: str | None = Field(default=None, max_length=20)
    text: str = Field(max_length=2000)
    urls: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def safe_urls(self) -> BibEntryOutput:
        if any(not (u.startswith("http://") or u.startswith("https://")) for u in self.urls):
            raise ValueError("urls must use http(s)")
        return self


class PdfBibV1(StrictModel):
    entries: list[BibEntryOutput] = Field(max_length=500)


class CiteMapping(StrictModel):
    marker: str = Field(max_length=120)
    entry_indices: list[Annotated[int, Field(ge=0)]] = Field(default_factory=list, max_length=20)


class PdfCiteMapV1(StrictModel):
    mappings: list[CiteMapping] = Field(max_length=1000)
