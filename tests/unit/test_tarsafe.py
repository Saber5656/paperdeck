import gzip
import io
import tarfile
from pathlib import Path

import pytest

from paperdeck.errors import SecurityError
from paperdeck.input.tarsafe import extract_tar, gunzip_file, sniff_kind


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


def test_rejects_links_devices_and_rolls_back_after_stream_cap(tmp_path: Path) -> None:
    archive = tmp_path / "links.tar"
    with tarfile.open(archive, "w") as tar:
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        tar.addfile(link)
    with pytest.raises(SecurityError) as exc:
        extract_tar(archive, tmp_path / "out", Limits())
    assert exc.value.code == "tar-link-escape"

    device_archive = tmp_path / "device.tar"
    with tarfile.open(device_archive, "w") as tar:
        device = tarfile.TarInfo("dev")
        device.type = tarfile.CHRTYPE
        tar.addfile(device)
    with pytest.raises(SecurityError) as exc:
        extract_tar(device_archive, tmp_path / "device-out", Limits())
    assert exc.value.code == "tar-special-member"

    oversized = tmp_path / "large.tar"
    make_tar(oversized, data=b"x" * (Limits.max_archive_total_mb * 1024 * 1024 + 1))
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep").write_text("keep")
    with pytest.raises(SecurityError) as exc:
        extract_tar(oversized, destination, Limits())
    assert exc.value.code == "archive-bomb"
    assert (destination / "keep").read_text() == "keep"


def test_gzip_single_bomb_leaves_no_output(tmp_path: Path) -> None:
    source = tmp_path / "source.gz"
    source.write_bytes(gzip.compress(b"x" * (2 * 1024 * 1024)))
    destination = tmp_path / "source.tex"
    with pytest.raises(SecurityError) as exc:
        gunzip_file(source, destination, 1)
    assert exc.value.code == "archive-bomb" and not destination.exists()


def test_allows_safe_relative_symlink_and_hardlink(tmp_path: Path) -> None:
    archive = tmp_path / "links.tar"
    with tarfile.open(archive, "w") as tar:
        source = tarfile.TarInfo("src/main.tex")
        payload = b"safe"
        source.size = len(payload)
        tar.addfile(source, io.BytesIO(payload))
        symlink = tarfile.TarInfo("src/current.tex")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "main.tex"
        tar.addfile(symlink)
        hardlink = tarfile.TarInfo("src/copy.tex")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "src/main.tex"
        tar.addfile(hardlink)

    destination = tmp_path / "out"
    files = extract_tar(archive, destination, Limits())

    assert files == [destination / "src/main.tex"]
    assert (destination / "src/current.tex").is_symlink()
    assert (destination / "src/current.tex").read_text() == "safe"
    assert (destination / "src/copy.tex").read_bytes() == b"safe"
    assert (
        (destination / "src/copy.tex").stat().st_ino
        == (destination / "src/main.tex").stat().st_ino
    )
