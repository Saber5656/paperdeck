"""Frozen Pydantic v2 models for paperdeck's intermediate representation."""

from __future__ import annotations

import base64
import re
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from paperdeck.errors import FallbackNote


class IRModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Text(IRModel):
    type: Literal["text"] = "text"
    text: str


class Emph(IRModel):
    type: Literal["emph"] = "emph"
    content: list[Inline]


class Strong(IRModel):
    type: Literal["strong"] = "strong"
    content: list[Inline]


class Sub(IRModel):
    type: Literal["sub"] = "sub"
    content: list[Inline]


class Sup(IRModel):
    type: Literal["sup"] = "sup"
    content: list[Inline]


class Code(IRModel):
    type: Literal["code"] = "code"
    text: str


class Math(IRModel):
    type: Literal["math"] = "math"
    latex: str


class RefLink(IRModel):
    type: Literal["ref_link"] = "ref_link"
    target_id: str
    kind: Literal["eq", "fig", "tab", "sec", "bib", "fn"]
    text: str


class Cite(IRModel):
    type: Literal["cite"] = "cite"
    bib_ids: list[str]
    text: str


class ExtLink(IRModel):
    type: Literal["ext_link"] = "ext_link"
    url: str
    content: list[Inline]

    @field_validator("url")
    @classmethod
    def allowed_scheme(cls, value: str) -> str:
        if urlparse(value).scheme.lower() not in {"https", "http", "mailto"}:
            raise ValueError("url scheme must be https, http, or mailto")
        return value


class FootnoteRef(IRModel):
    type: Literal["footnote_ref"] = "footnote_ref"
    target_id: str
    number: str


class LineBreak(IRModel):
    type: Literal["line_break"] = "line_break"


Inline = Annotated[
    Text
    | Emph
    | Strong
    | Sub
    | Sup
    | Code
    | Math
    | RefLink
    | Cite
    | ExtLink
    | FootnoteRef
    | LineBreak,
    Field(discriminator="type"),
]


class Source(IRModel):
    kind: Literal["arxiv", "local"]
    original: str
    arxiv_id: str | None = None
    version: str | None = None


class LlmProvenance(IRModel):
    model: str
    vlm_model: str | None = None
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = 0.0


class Provenance(IRModel):
    engine: str
    engine_versions: dict[str, str]
    created_at: str
    fallbacks: list[FallbackNote]
    llm: LlmProvenance | None = None


class MetaLink(IRModel):
    url: str
    kind: Literal["arxiv", "doi", "generic"]

    @field_validator("url")
    @classmethod
    def allowed_scheme(cls, value: str) -> str:
        if urlparse(value).scheme.lower() not in {"https", "http", "mailto"}:
            raise ValueError("url scheme must be https, http, or mailto")
        return value


class Meta(IRModel):
    title: list[Inline]
    authors: list[str]
    abstract: list[Block] | None = None
    links: list[MetaLink]


class Cell(IRModel):
    type: Literal["cell"] = "cell"
    content: list[Inline]
    header: bool = False
    colspan: int = Field(default=1, ge=1)
    rowspan: int = Field(default=1, ge=1)


class Section(IRModel):
    type: Literal["section"] = "section"
    id: str
    level: int = Field(ge=1, le=6)
    number: str | None = None
    title: list[Inline]
    children: list[Block]


class Paragraph(IRModel):
    type: Literal["paragraph"] = "paragraph"
    id: str
    content: list[Inline]


class Equation(IRModel):
    type: Literal["equation"] = "equation"
    id: str
    number: str | None = None
    label: str | None = None
    content_kind: Literal["latex", "image"]
    latex: str | None = None
    asset_id: str | None = None
    latex_verified: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_content(self) -> Equation:
        if self.content_kind == "latex":
            if not self.latex or not self.latex_verified or self.asset_id is not None:
                raise ValueError(
                    "latex equation requires latex, latex_verified=true, and no asset_id"
                )
        elif self.asset_id is None or self.latex_verified:
            raise ValueError("image equation requires asset_id and latex_verified=false")
        return self


class Figure(IRModel):
    type: Literal["figure"] = "figure"
    id: str
    number: str | None = None
    label: str | None = None
    asset_id: str | None = None
    caption: list[Inline]
    alt_text: str | None = None


class Table(IRModel):
    type: Literal["table"] = "table"
    id: str
    number: str | None = None
    label: str | None = None
    caption: list[Inline]
    content_kind: Literal["grid", "image"]
    rows: list[list[Cell]] | None = None
    asset_id: str | None = None

    @model_validator(mode="after")
    def validate_content(self) -> Table:
        if self.content_kind == "grid" and self.rows is None:
            raise ValueError("grid table requires rows")
        if self.content_kind == "image" and self.asset_id is None:
            raise ValueError("image table requires asset_id")
        return self


class ListBlock(IRModel):
    type: Literal["list"] = "list"
    id: str
    ordered: bool
    items: list[list[Block]]


class Quote(IRModel):
    type: Literal["quote"] = "quote"
    id: str
    content: list[Block]


class CodeBlock(IRModel):
    type: Literal["code_block"] = "code_block"
    id: str
    text: str
    language: str | None = None


class FootnoteDef(IRModel):
    type: Literal["footnote_def"] = "footnote_def"
    id: str
    number: str
    content: list[Block]


class Unhandled(IRModel):
    type: Literal["unhandled"] = "unhandled"
    id: str
    text: str


class BibUrl(IRModel):
    url: str
    kind: Literal["doi", "arxiv", "generic"]

    @field_validator("url")
    @classmethod
    def allowed_scheme(cls, value: str) -> str:
        if urlparse(value).scheme.lower() not in {"https", "http", "mailto"}:
            raise ValueError("url scheme must be https, http, or mailto")
        return value


class BibEntry(IRModel):
    type: Literal["bib_entry"] = "bib_entry"
    id: str
    number: str | None = None
    label: str | None = None
    key: str | None = None
    content: list[Inline]
    urls: list[BibUrl]


Block = Annotated[
    Section
    | Paragraph
    | Equation
    | Figure
    | Table
    | ListBlock
    | Quote
    | CodeBlock
    | FootnoteDef
    | Unhandled,
    Field(discriminator="type"),
]


class Warning(IRModel):
    code: str
    message: str
    where: str | None = None


class AssetOrigin(IRModel):
    engine: str
    source_path: str | None = None
    page: int | None = None


_B64_RE = re.compile(r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")


class Asset(IRModel):
    id: str
    mime: Literal["image/png", "image/jpeg", "image/svg+xml"]
    data_b64: str
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    origin: AssetOrigin

    @field_validator("data_b64")
    @classmethod
    def valid_base64(cls, value: str) -> str:
        if not value or not _B64_RE.fullmatch(value):
            raise ValueError("data_b64 must be non-empty padded base64")
        try:
            base64.b64decode(value, validate=True)
        except ValueError as exc:
            raise ValueError("data_b64 must be valid base64") from exc
        return value


class Document(IRModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={"$id": "https://github.com/Saber5656/paperdeck/schema/ir-v1.json"},
    )
    schema_version: Literal["1"] = "1"
    source: Source
    provenance: Provenance
    meta: Meta
    macros: dict[str, str] = Field(default_factory=dict)
    body: list[Block]
    bibliography: list[BibEntry] = Field(default_factory=list)
    footnotes: list[FootnoteDef] = Field(default_factory=list)
    assets: dict[str, Asset] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    warnings: list[Warning] = Field(default_factory=list)


for _model in (
    Emph,
    Strong,
    Sub,
    Sup,
    ExtLink,
    Meta,
    Section,
    Paragraph,
    ListBlock,
    Quote,
    FootnoteDef,
    Document,
):
    _model.model_rebuild()
