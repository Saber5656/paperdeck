import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SHA = re.compile(r"^[0-9a-f]{40}$")


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text()


def test_actions_are_sha_pinned_and_workflows_are_read_only() -> None:
    for name in ("ci.yml", "release.yml"):
        text = _workflow(name)
        for ref in re.findall(r"uses:\s*([^\s#]+)", text):
            if not ref.startswith("./"):
                assert "@" in ref and SHA.fullmatch(ref.rsplit("@", 1)[1]), (name, ref)
        assert re.search(r"permissions:\s*\n\s+contents:\s*read", text)
        assert "cancel-in-progress: true" in text


def test_release_only_grants_oidc_to_publish_and_requires_stable_pypi() -> None:
    text = _workflow("release.yml")
    assert "^v[0-9]+\\.[0-9]+\\.[0-9]+$" in text
    assert "id-token: write" in text
    assert text.index("id-token: write") > text.index("publish:")
    assert "environment: pypi" in text
    assert "stable == 'true'" in text


def test_version_is_hatch_dynamic_from_package_source() -> None:
    text = (ROOT / "pyproject.toml").read_text()
    assert 'dynamic = ["version"]' in text
    assert "[tool.hatch.version]" in text
    assert 'path = "src/paperdeck/__init__.py"' in text
    assert not re.search(r"^version\s*=", text, re.MULTILINE)
