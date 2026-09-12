"""Issue 02/05/06/09 contract tests over errors, IR traversal and cache IO."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from paperdeck.config import LimitsSettings
from paperdeck.errors import (
    EXIT_CODES,
    AllEnginesFailedError,
    ConfigError,
    ConversionError,
    CostLimitError,
    FallbackNote,
    FetchError,
    InputError,
    LlmError,
    OutputExistsError,
    SecurityError,
    present_error,
)
from paperdeck.input.cache import CacheManager
from paperdeck.ir.anchors import AnchorAllocator
from paperdeck.ir.model import (
    Asset,
    AssetOrigin,
    BibEntry,
    BibUrl,
    Cell,
    Cite,
    Code,
    CodeBlock,
    Document,
    Emph,
    Equation,
    ExtLink,
    Figure,
    FootnoteDef,
    FootnoteRef,
    LineBreak,
    ListBlock,
    Math,
    Meta,
    MetaLink,
    Paragraph,
    Provenance,
    Quote,
    RefLink,
    Section,
    Source,
    Strong,
    Sub,
    Sup,
    Table,
    Text,
    Unhandled,
    Warning,
)
from paperdeck.ir.validate import iter_blocks, iter_inlines, validate_document


def _asset(asset_id: str, data: str = "aGk=") -> Asset:
    return Asset(id=asset_id, mime="image/png", data_b64=data, origin=AssetOrigin(engine="test"))


def _full_document() -> Document:
    inline = [
        Text(text="text"),
        Emph(content=[Strong(content=[Text(text="strong")])]),
        Sub(content=[Text(text="sub")]),
        Sup(content=[Text(text="sup")]),
        Code(text="code"),
        Math(latex="x"),
        RefLink(target_id="eq-1", kind="eq", text="Eq. 1"),
        Cite(bib_ids=["bib-1"], text="[1]"),
        ExtLink(url="https://example.test", content=[Text(text="link")]),
        FootnoteRef(target_id="fn-1", number="1"),
        LineBreak(),
    ]
    cell = Cell(content=[Text(text="cell")], header=True, colspan=2, rowspan=1)
    children = [
        Paragraph(id="para-1", content=inline),
        Equation(id="eq-1", content_kind="latex", latex="x=y", latex_verified=True),
        Equation(id="eq-img", content_kind="image", asset_id="asset-1"),
        Figure(id="fig-1", asset_id="asset-1", caption=[Text(text="fig")]),
        Table(id="tab-1", content_kind="grid", rows=[[cell]], caption=[]),
        Table(id="tab-img", content_kind="image", asset_id="asset-1", caption=[]),
        ListBlock(
            id="list-1",
            ordered=True,
            items=[[Paragraph(id="para-list", content=[Text(text="item")])]],
        ),
        Quote(id="quote-1", content=[CodeBlock(id="code-block", text="print(1)")]),
        FootnoteDef(id="fn-1", number="1", content=[Unhandled(id="unhandled-1", text="raw")]),
    ]
    return Document(
        source=Source(kind="local", original="paper.pdf"),
        provenance=Provenance(engine="test", engine_versions={}, created_at="now", fallbacks=[]),
        meta=Meta(
            title=[Text(text="title")],
            authors=["Author"],
            abstract=[Paragraph(id="abstract-1", content=[Text(text="abstract")])],
            links=[MetaLink(url="https://example.test", kind="generic")],
        ),
        body=[
            Section(
                id="sec-1", level=1, number="1", title=[Text(text="Section")], children=children
            )
        ],
        bibliography=[
            BibEntry(
                id="bib-1",
                number="1",
                key="key",
                content=[Text(text="entry")],
                urls=[BibUrl(url="https://example.test", kind="generic")],
            )
        ],
        assets={"asset-1": _asset("asset-1"), "asset-orphan": _asset("asset-orphan")},
        labels={"intro": "sec-1"},
        warnings=[Warning(code="fixture", message="fixture")],
    )


def test_all_ir_nodes_roundtrip_and_walker_order() -> None:
    document = _full_document()
    rebuilt = Document.model_validate(document.model_dump())
    assert rebuilt == document
    block_ids = [block.id for block in iter_blocks(document)]
    assert block_ids == [
        "sec-1",
        "para-1",
        "eq-1",
        "eq-img",
        "fig-1",
        "tab-1",
        "tab-img",
        "list-1",
        "para-list",
        "quote-1",
        "code-block",
        "fn-1",
        "unhandled-1",
    ]
    inline_types = [item.type for item in iter_inlines(document.body[0].children[0])]
    assert inline_types == [
        "text",
        "emph",
        "strong",
        "text",
        "sub",
        "text",
        "sup",
        "text",
        "code",
        "math",
        "ref_link",
        "cite",
        "ext_link",
        "text",
        "footnote_ref",
        "line_break",
    ]


def test_ir_security_invariants_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="javascript"):
        BibUrl(url="javascript:alert(1)", kind="generic")
    with pytest.raises(ValidationError, match="additional|extra"):
        Paragraph(id="p", content=[], extra="bad")
    with pytest.raises(ValidationError, match="data_b64"):
        _asset("bad", "not base64")
    with pytest.raises(ValidationError, match="colspan"):
        Cell(content=[], colspan=0)
    with pytest.raises(ValidationError, match="frozen"):
        document = _full_document()
        document.meta = document.meta
    with pytest.raises(ConversionError, match="unknown anchor"):
        validate_document(
            _full_document().model_copy(update={"labels": {"bad": "missing"}}), LimitsSettings()
        )


def test_validation_warning_contracts() -> None:
    document = _full_document()
    warnings = validate_document(document, LimitsSettings())
    codes = {item.code for item in warnings}
    assert "orphan-asset" in codes
    empty = Section(id="empty", level=1, title=[], children=[])
    base = document.model_copy(update={"body": [empty], "assets": {}, "labels": {}})
    assert any(item.code == "empty-section" for item in validate_document(base, LimitsSettings()))
    inert = Paragraph(id="p", content=[RefLink(target_id="", kind="sec", text="?")])
    fn = FootnoteDef(
        id="fn",
        number="1",
        content=[Paragraph(id="fp", content=[FootnoteRef(target_id="", number="1")])],
    )
    doc = document.model_copy(
        update={"body": [inert], "footnotes": [fn], "assets": {}, "labels": {}}
    )
    codes = {item.code for item in validate_document(doc, LimitsSettings())}
    assert "unresolved-ref" in codes

    unnumbered = Equation(id="eq-unnum", content_kind="latex", latex="x", latex_verified=True)
    eqref = Paragraph(id="eqref", content=[RefLink(target_id="eq-unnum", kind="eq", text="?")])
    eq_doc = document.model_copy(update={"body": [unnumbered, eqref], "assets": {}, "labels": {}})
    assert any(
        item.code == "unnumbered-eqref-target"
        for item in validate_document(eq_doc, LimitsSettings())
    )

    large = _asset("large", "A" * 2_000_000)
    large_doc = document.model_copy(
        update={
            "body": [Figure(id="fig-large", asset_id="large", caption=[])],
            "assets": {"large": large},
            "labels": {},
        }
    )
    limited = LimitsSettings(embed_warn_mb=1, embed_hard_max_mb=1)
    assert any(item.code == "assets-over-budget" for item in validate_document(large_doc, limited))


def test_validation_hard_failures_cover_cites_and_duplicate_ids() -> None:
    document = _full_document()
    bad_cite = Paragraph(id="bad", content=[Cite(bib_ids=["missing"], text="x")])
    with pytest.raises(ConversionError, match="bibliography"):
        validate_document(document.model_copy(update={"body": [bad_cite]}), LimitsSettings())
    duplicate = Paragraph(id="sec-1", content=[])
    with pytest.raises(ConversionError, match="duplicate"):
        validate_document(
            document.model_copy(update={"body": [document.body[0], duplicate]}), LimitsSettings()
        )
    assert AnchorAllocator().next("eq") == "eq-1"
    with pytest.raises(ValueError, match="unknown"):
        AnchorAllocator().next("bad")

    missing_asset = document.model_copy(
        update={"body": [Figure(id="fig-missing", asset_id="missing", caption=[])], "labels": {}}
    )
    with pytest.raises(ConversionError, match="unknown asset_id"):
        validate_document(missing_asset, LimitsSettings())
    missing_ref = document.model_copy(
        update={
            "body": [
                Paragraph(id="ref", content=[RefLink(target_id="missing", kind="sec", text="?")])
            ],
            "labels": {},
        }
    )
    with pytest.raises(ConversionError, match="RefLink"):
        validate_document(missing_ref, LimitsSettings())
    missing_footnote = document.model_copy(
        update={
            "body": [
                Paragraph(
                    id="footnote-ref",
                    content=[FootnoteRef(target_id="missing", number="?")],
                )
            ],
            "labels": {},
        }
    )
    with pytest.raises(ConversionError, match="FootnoteRef"):
        validate_document(missing_footnote, LimitsSettings())
    invalid_equation = Equation.model_construct(
        id="eq-invalid", content_kind="image", latex=None, asset_id=None, latex_verified=False
    )
    invalid_doc = document.model_copy(update={"body": [invalid_equation], "labels": {}})
    with pytest.raises(ConversionError, match="equation invariant"):
        validate_document(invalid_doc, LimitsSettings())


def test_error_subclasses_have_exit_codes_and_presenter_hygiene() -> None:
    attempts = [FallbackNote("pdf", "bad", "detail"), FallbackNote("latex", "bad2", "detail2")]
    error = AllEnginesFailedError("failed", "retry", attempts)
    rendered, code = present_error(error)
    assert code == 5 and "ENGINE" in rendered and rendered.index("pdf") < rendered.index("latex")
    for cls, expected in {
        InputError: 3,
        FetchError: 4,
        ConversionError: 5,
        AllEnginesFailedError: 5,
        LlmError: 6,
        CostLimitError: 7,
        ConfigError: 8,
        SecurityError: 9,
        OutputExistsError: 10,
    }.items():
        assert EXIT_CODES[cls] == expected
    safe, code = present_error(SecurityError("x\x1b[31m" + "A" * 10000, "fix"), 0)
    assert code == 9
    assert "\x1b" not in safe and "[31m" not in safe and len(safe) <= 200
    debug, debug_code = present_error(error, 2)
    assert debug_code == 5 and "AllEnginesFailedError" in debug
    assert "AllEnginesFailedError" not in rendered


def test_anchor_allocator_sequences_each_kind_and_replays_stably() -> None:
    kinds = ("sec", "sec", "eq", "para", "eq")
    expected = ["sec-1", "sec-2", "eq-1", "para-1", "eq-2"]
    allocator = AnchorAllocator()
    assert [allocator.next(kind) for kind in kinds] == expected
    replay = AnchorAllocator()
    assert [replay.next(kind) for kind in kinds] == expected


def test_cache_atomic_crash_cleanup_and_permissions(tmp_path: Path, monkeypatch) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    stale = cache.root / "arxiv" / "2401.12345" / "1" / "meta.xml.tmp"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")
    cache.put("arxiv/2401.12345/1/meta.xml", b"fresh")
    assert cache.get("arxiv/2401.12345/1/meta.xml").read_bytes() == b"fresh"
    assert not stale.exists()
    llm = cache.put("llm/model/name/result.json", b"secret")
    assert os.stat(llm).st_mode & 0o777 == 0o600
    assert os.stat(cache.root / "llm").st_mode & 0o777 == 0o700
    assert os.stat(cache.root / "llm" / "model").st_mode & 0o777 == 0o700
    assert os.stat(cache.root / "llm" / "model" / "name").st_mode & 0o777 == 0o700
    assert os.stat(cache.root / "arxiv").st_mode & 0o777 == 0o755
    assert os.stat(cache.root / "arxiv" / "2401.12345").st_mode & 0o777 == 0o755
    assert os.stat(cache.root / "arxiv" / "2401.12345" / "1").st_mode & 0o777 == 0o755
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    copied = cache.put("arxiv/2401.12345/1/source.pdf", source)
    assert copied.read_bytes() == b"source" and os.stat(copied).st_mode & 0o777 == 0o644
    atomic = cache.put("arxiv/2401.12345/1/atomic.bin", b"old")
    monkeypatch.setattr(
        "paperdeck.input.cache.os.replace", lambda *_args: (_ for _ in ()).throw(OSError("crash"))
    )
    with pytest.raises(OSError):
        cache.put("arxiv/2401.12345/1/atomic.bin", b"new")
    assert atomic.read_bytes() == b"old"
    assert not (cache.root / "arxiv/2401.12345/1/atomic.bin.tmp").exists()
    assert not list((cache.root / "arxiv/2401.12345/1").glob("atomic.bin.tmp.*"))


def test_cache_entries_versions_promote_and_clear_scope(tmp_path: Path) -> None:
    root = tmp_path / "paperdeck"
    cache = CacheManager(root)
    cache.put("arxiv/hep-th--9901001/latest-unknown/meta.xml", b"meta")
    cache.put("arxiv/hep-th--9901001/latest-unknown/paper.pdf", b"pdf")
    cache.put("arxiv/2401.12345/1/paper.pdf", b"one")
    assert cache.versions("2401.12345") == [1]
    promoted = cache.promote("hep-th/9901001", 2)
    assert promoted.joinpath("meta.xml").exists() and cache.entries()[0].version == 1
    cache.clear("2401.12345")
    assert not (root / "arxiv" / "2401.12345").exists()
    assert promoted.exists()
    with pytest.raises(SecurityError):
        cache.clear("../escape")


def test_cache_rejects_symlink_escape_for_read_and_write(tmp_path: Path) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    outside = tmp_path / "outside"
    outside.mkdir()
    cache.root.joinpath("arxiv").mkdir(parents=True)
    cache.root.joinpath("arxiv", "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SecurityError, match="cache path"):
        cache.put("arxiv/escape/payload.bin", b"secret")
    with pytest.raises(SecurityError, match="cache path"):
        cache.get("arxiv/escape/payload.bin")
    assert not outside.joinpath("payload.bin").exists()
