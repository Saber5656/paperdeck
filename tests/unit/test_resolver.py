from pathlib import Path

import pytest

from paperdeck.errors import InputError
from paperdeck.input.resolver import InputSpec, output_slug, resolve


@pytest.mark.parametrize(
    "raw, ident, version",
    [
        ("2401.1234", "2401.1234", None),
        ("2401.12345v2", "2401.12345", 2),
        ("arXiv:2401.12345", "2401.12345", None),
        ("arxiv:hep-th/9901001v3", "hep-th/9901001", 3),
        ("hep-th/9901001", "hep-th/9901001", None),
        ("https://arxiv.org/abs/2401.12345", "2401.12345", None),
        ("http://www.arxiv.org/pdf/2401.12345.pdf", "2401.12345", None),
        ("https://export.arxiv.org/html/hep-th/9901001v2", "hep-th/9901001", 2),
    ],
)
def test_arxiv_forms(raw: str, ident: str, version: int | None) -> None:
    result = resolve(raw)
    assert result.kind == "arxiv"
    assert result.arxiv_id == ident and result.version == version


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://arxiv.org/abs/2401.12345",
        "https://evil.example/abs/2401.12345",
        "24010.1234",
        "word.docx",
        "not an id",
    ],
)
def test_rejects_unrecognized(raw: str) -> None:
    with pytest.raises(InputError) as exc:
        resolve(raw)
    assert "2401.12345" in exc.value.hint


def test_local_path_first_and_slug(tmp_path: Path) -> None:
    paper = tmp_path / "2401.12345"
    paper.write_text("x")
    with pytest.raises(InputError):
        resolve(str(paper))
    tex = tmp_path / "my paper.tex"
    tex.write_text("x")
    spec = resolve(str(tex))
    assert spec.kind == "latex-local"
    assert output_slug(spec) == "my-paper"
    assert (
        output_slug(InputSpec("arxiv", arxiv_id="hep-th/9901001", version=2))
        == "arxiv-hep-th-9901001v2"
    )
