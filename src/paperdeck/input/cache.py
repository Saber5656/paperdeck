"""Atomic XDG cache management.

Version 1 deliberately has no process lock. Concurrent runs can duplicate a
download, but each individual file is installed atomically.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import SecurityError

_KEY = re.compile(r"^[A-Za-z0-9._/-]+$")
_MODEL = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class CacheEntry:
    id: str
    version: int | None
    kinds: tuple[str, ...]
    total_bytes: int


class CacheManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._chmod(self.root, 0o755)

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError:
            pass

    @staticmethod
    def _id_part(arxiv_id: str) -> str:
        return arxiv_id.replace("/", "--")

    def arxiv_dir(self, arxiv_id: str, version: int | None) -> Path:
        if (
            not arxiv_id
            or "\x00" in arxiv_id
            or Path(arxiv_id).is_absolute()
            or ".." in Path(arxiv_id).parts
        ):
            raise SecurityError(
                "Invalid arXiv cache identifier",
                "use a valid arXiv identifier",
                "cache-key-invalid",
            )
        version_name = "latest-unknown" if version is None else str(int(version))
        return self.root / "arxiv" / self._id_part(arxiv_id) / version_name

    def llm_dir(self, model: str) -> Path:
        return self.root / "llm" / _MODEL.sub("_", model)

    def _path(self, path_key: str) -> Path:
        if (
            not isinstance(path_key, str)
            or "\x00" in path_key
            or path_key.startswith("/")
            or not _KEY.fullmatch(path_key)
            or ".." in path_key.split("/")
        ):
            raise SecurityError(
                "Invalid cache path",
                "use a relative cache path without parent segments",
                "cache-key-invalid",
            )
        path = self.root / Path(path_key)
        try:
            path.resolve(strict=False).relative_to(self.root.resolve(strict=False))
        except (OSError, RuntimeError, ValueError):
            raise SecurityError(
                "Invalid cache path",
                "use a relative cache path without parent segments",
                "cache-key-invalid",
            ) from None
        return path

    def put(self, path_key: str, source: Path | bytes) -> Path:
        destination = self._path(path_key)
        self._ensure_root()
        destination.parent.mkdir(parents=True, exist_ok=True)
        is_llm = path_key.startswith("llm/")
        directory_root = self.root / ("llm" if is_llm else "arxiv")
        if is_llm:
            directory_mode = 0o700
        else:
            directory_mode = 0o755
        current = destination.parent
        while True:
            self._chmod(current, directory_mode)
            if current == directory_root:
                break
            current = current.parent
        # Older versions used a fixed ``.tmp`` name, so a process killed after
        # writing can leave it behind.  Remove only that legacy name; current
        # writers use unique names and therefore never remove another active
        # writer's temporary file.
        legacy_temporary = destination.with_name(destination.name + ".tmp")
        try:
            legacy_temporary.unlink()
        except FileNotFoundError:
            pass
        fd, temporary_name = tempfile.mkstemp(
            prefix=destination.name + ".tmp.", dir=str(destination.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as output:
                if isinstance(source, bytes):
                    output.write(source)
                else:
                    with Path(source).open("rb") as input_file:
                        shutil.copyfileobj(input_file, output)
                output.flush()
                os.fsync(output.fileno())
            self._chmod(temporary, 0o600 if is_llm else 0o644)
            os.replace(temporary, destination)
            self._chmod(destination, 0o600 if is_llm else 0o644)
            try:
                dir_fd = os.open(destination.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return destination

    def get(self, path_key: str) -> Path | None:
        path = self._path(path_key)
        return path if path.is_file() else None

    def exists(self, path_key: str) -> bool:
        return self.get(path_key) is not None

    def versions(self, arxiv_id: str) -> list[int]:
        parent = self.root / "arxiv" / self._id_part(arxiv_id)
        result: list[int] = []
        if parent.is_dir():
            for child in parent.iterdir():
                if child.is_dir() and child.name.isdigit():
                    result.append(int(child.name))
        return sorted(result)

    def entries(self) -> list[CacheEntry]:
        base = self.root / "arxiv"
        entries: list[CacheEntry] = []
        if not base.is_dir():
            return entries
        for id_dir in sorted(base.iterdir()):
            if not id_dir.is_dir():
                continue
            arxiv_id = id_dir.name.replace("--", "/")
            for version_dir in sorted(id_dir.iterdir()):
                if not version_dir.is_dir():
                    continue
                version = int(version_dir.name) if version_dir.name.isdigit() else None
                kinds: list[str] = []
                total = 0
                for path in version_dir.rglob("*"):
                    if path.is_file() and not path.name.endswith(".tmp"):
                        total += path.stat().st_size
                        if path.name in {
                            "meta.xml",
                            "source.tar.gz",
                            "source.tex",
                            "source.pdf",
                            "paper.pdf",
                            "index.html",
                        }:
                            kinds.append(path.name)
                entries.append(CacheEntry(arxiv_id, version, tuple(sorted(set(kinds))), total))
        return entries

    def promote(self, arxiv_id: str, resolved_version: int) -> Path:
        if resolved_version < 1:
            raise SecurityError(
                "Invalid cache version", "use a positive arXiv version", "cache-key-invalid"
            )
        unknown = self.arxiv_dir(arxiv_id, None)
        target = self.arxiv_dir(arxiv_id, resolved_version)
        if not unknown.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        self._chmod(target.parent, 0o755)
        if not target.exists():
            os.replace(unknown, target)
            return target
        # A concurrent/latest fetch may have populated the target already. Keep
        # its files and move any missing files from the transient directory.
        for item in unknown.iterdir():
            destination = target / item.name
            if not destination.exists():
                os.replace(item, destination)
        try:
            unknown.rmdir()
        except OSError:
            shutil.rmtree(unknown)
        return target

    def clear(self, arxiv_id: str | None = None) -> None:
        if self.root.name != "paperdeck":
            raise SecurityError(
                "Refusing to clear an unrecognized cache root",
                "set the cache root to a paperdeck directory",
                "cache-root-invalid",
            )
        if not self.root.exists():
            return
        if arxiv_id is None:
            for child in self.root.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            return
        if (
            not arxiv_id
            or "\x00" in arxiv_id
            or Path(arxiv_id).is_absolute()
            or ".." in Path(arxiv_id).parts
        ):
            raise SecurityError(
                "Invalid arXiv cache identifier",
                "use a valid arXiv identifier",
                "cache-key-invalid",
            )
        ident = self._id_part(arxiv_id)
        target = self.root / "arxiv" / ident
        target.relative_to(self.root / "arxiv")
        if target.is_dir():
            shutil.rmtree(target)
