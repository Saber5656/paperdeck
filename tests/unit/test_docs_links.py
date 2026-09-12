import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_public_docs_and_relative_links_exist() -> None:
    for name in ("README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md"):
        assert (ROOT / name).is_file()
    for doc in (ROOT / "README.md", ROOT / "CONTRIBUTING.md"):
        for target in re.findall(r"\[[^]]+\]\(([^)#]+)", doc.read_text()):
            if target.startswith(("http://", "https://")):
                continue
            assert (doc.parent / target).resolve().exists(), target


def test_security_contract_is_explicit() -> None:
    security = (ROOT / "SECURITY.md").read_text()
    assert "python -m paperdeck.render.validate out.html" in security
    assert "zero external" in security.lower()
    assert "T3" in security
