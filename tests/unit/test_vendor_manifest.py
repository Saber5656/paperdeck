import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/vendor_katex.py"
spec = importlib.util.spec_from_file_location("vendor_katex", SCRIPT)
vendor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor)


def archive(name, data=b"hello"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        member = tarfile.TarInfo(name)
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    return buf.getvalue()


def test_archive_checksum_rejected():
    with pytest.raises(ValueError, match="checksum"):
        vendor.unpack(archive("katex/katex.min.js"), "bad")


@pytest.mark.parametrize("name", ["../escape", "/etc/escape", "katex/../escape"])
def test_archive_path_rejected(name):
    data = archive(name)
    with pytest.raises(ValueError, match="path"):
        vendor.unpack(data, hashlib.sha256(data).hexdigest())


def test_only_selected_assets():
    data = archive("katex/katex.min.js")
    assert vendor.unpack(data, hashlib.sha256(data).hexdigest()) == {"katex.min.js": b"hello"}


def test_vendor_checksums_and_tamper(tmp_path):
    root = SCRIPT.parents[1] / "src/paperdeck/render/assets/vendor/katex"
    assert vendor.verify_vendored(root) == []
    import shutil

    shutil.copytree(root, tmp_path / "katex")
    (tmp_path / "katex/katex.min.js").write_bytes(b"tampered")
    assert "katex.min.js" in vendor.verify_vendored(tmp_path / "katex")
