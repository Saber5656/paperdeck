import io
import tarfile
from pathlib import Path

import pytest

from paperdeck.errors import SecurityError
from paperdeck.input.tarsafe import extract_tar, sniff_kind


class Limits:
    max_archive_members = 20
    max_archive_total_mb = 1


def make_tar(
    path: Path, name: str = "src/main.tex", data: bytes = b"\\documentclass{article}"
) -> None:
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


def test_happy_path_and_sniff(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar"
    make_tar(archive)
    assert sniff_kind(archive) == "tar"
    dest = tmp_path / "out"
    files = extract_tar(archive, dest, Limits())
    assert files == [dest / "src/main.tex"]
    assert (dest / "src/main.tex").read_bytes().startswith(b"\\documentclass")


@pytest.mark.parametrize(
    "name, code", [("/etc/passwd", "tar-path-invalid"), ("../../escape", "tar-path-invalid")]
)
def test_rejects_traversal(tmp_path: Path, name: str, code: str) -> None:
    archive = tmp_path / "bad.tar"
    make_tar(archive, name)
    with pytest.raises(SecurityError) as exc:
        extract_tar(archive, tmp_path / "out", Limits())
    assert exc.value.code == code
    assert not (tmp_path / "out").exists()
