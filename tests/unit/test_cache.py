from pathlib import Path

import pytest

from paperdeck.errors import SecurityError
from paperdeck.input.cache import CacheManager


def test_atomic_put_and_promote(tmp_path: Path) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    path = cache.put("arxiv/hep-th--9901001/latest-unknown/meta.xml", b"<entry/>")
    assert path.read_bytes() == b"<entry/>"
    promoted = cache.promote("hep-th/9901001", 2)
    assert promoted.joinpath("meta.xml").exists()
    assert cache.promote("hep-th/9901001", 2) == promoted


@pytest.mark.parametrize("key", ["../escape.bin", "/abs.bin", "x\x00y", "a/../../x"])
def test_path_confinement(tmp_path: Path, key: str) -> None:
    cache = CacheManager(tmp_path / "paperdeck")
    with pytest.raises(SecurityError) as exc:
        cache.put(key, b"x")
    assert exc.value.code == "cache-key-invalid"


def test_clear_guard_and_entries(tmp_path: Path) -> None:
    root = tmp_path / "paperdeck"
    cache = CacheManager(root)
    cache.put("arxiv/2401.12345/1/paper.pdf", b"pdf")
    assert cache.entries()[0].total_bytes == 3
    cache.clear()
    assert root.exists() and not (root / "arxiv").exists()
    with pytest.raises(SecurityError):
        CacheManager(tmp_path).clear()


def test_cache_copy_source_llm_permissions_and_scoped_clear(tmp_path: Path) -> None:
    root = tmp_path / "paperdeck"
    cache = CacheManager(root)
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    path = cache.put("arxiv/2401.12345/2/source.tex", source)
    assert cache.get("arxiv/2401.12345/2/source.tex") == path
    cache.put("llm/model/request.json", b"secret")
    assert (root / "llm").stat().st_mode & 0o777 == 0o700
    cache.put("arxiv/2401.12345/3/meta.xml", b"new")
    cache.clear("2401.12345")
    assert not (root / "arxiv" / "2401.12345").exists()
    assert cache.exists("llm/model/request.json")


def test_promote_merges_existing_target_and_rejects_bad_version(tmp_path: Path) -> None:
    root = tmp_path / "paperdeck"
    cache = CacheManager(root)
    cache.put("arxiv/2401.12345/latest-unknown/meta.xml", b"meta")
    cache.put("arxiv/2401.12345/2/source.tex", b"tex")
    target = cache.promote("2401.12345", 2)
    assert (target / "meta.xml").exists() and (target / "source.tex").exists()
    with pytest.raises(SecurityError) as exc:
        cache.promote("2401.12345", 0)
    assert exc.value.code == "cache-key-invalid"
