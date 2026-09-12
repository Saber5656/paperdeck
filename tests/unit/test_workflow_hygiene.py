import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from paperdeck import __version__

ROOT = Path(__file__).parents[2]
SHA = re.compile(r"^[0-9a-f]{40}$")
BASE_VERSION = __version__.split(".dev", 1)[0].split("rc", 1)[0]


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


def test_ci_does_not_reference_secrets() -> None:
    assert "secrets." not in _workflow("ci.yml")


def test_version_is_hatch_dynamic_from_package_source() -> None:
    text = (ROOT / "pyproject.toml").read_text()
    assert 'dynamic = ["version"]' in text
    assert "[tool.hatch.version]" in text
    assert 'path = "src/paperdeck/__init__.py"' in text
    assert not re.search(r"^version\s*=", text, re.MULTILINE)


@pytest.mark.parametrize(
    ("tag", "allowed"),
    [
        (f"v{BASE_VERSION}-rc.1", True),
        ("v9999.0.0-rc.1", False),
        (f"v{BASE_VERSION}", __version__ == BASE_VERSION),
    ],
)
def test_release_version_guard_executes_before_publish(tag, allowed):
    # Exercise the actual workflow program against the current development version.
    source = _workflow("release.yml").split("uv run python - <<'PY'\n", 1)[1]
    source = textwrap.dedent(source.split("          PY\n", 1)[0])
    result = subprocess.run(
        [sys.executable, "-c", source],
        env={**os.environ, "TAG": tag},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) is allowed, result.stdout + result.stderr
