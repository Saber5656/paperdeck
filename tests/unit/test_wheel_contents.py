import subprocess
import zipfile
from pathlib import Path


def test_wheel_contains_reader_assets_and_excludes_source_tests(tmp_path: Path) -> None:
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)], check=True)
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    required = {
        "paperdeck/render/templates/document.html.j2",
        "paperdeck/render/assets/viewer.js",
        "paperdeck/render/assets/viewer.css",
        "paperdeck/render/assets/vendor/katex/MANIFEST.json",
        "paperdeck/render/assets/vendor/katex/LICENSE",
        "paperdeck/ir/schema/ir-v1.json",
        "paperdeck/llm/prompts/segment.md",
        "paperdeck/llm/schemas/pdf_segment.v1.json",
    }
    assert required <= names
    assert not any(name.startswith(("tests/", "paperdeck/tests/")) for name in names)
    assert not any(name.endswith(".pyc") or "__pycache__" in name for name in names)
