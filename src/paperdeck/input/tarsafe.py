"""Hardened tar and gzip extraction for untrusted arXiv e-prints."""

from __future__ import annotations

import gzip
import os
import shutil
import tarfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Literal

from ..errors import SecurityError

Kind = Literal["tar-gz", "tar", "gzip-single", "pdf", "tex", "unknown"]


def _member_name(name: str) -> str:
    clean = "".join(ch if ch.isprintable() and ch not in "\r\n\t" else "?" for ch in name)
    return clean[:120]


def _security(code: str, name: str) -> SecurityError:
    return SecurityError(
        f"Unsafe archive member {_member_name(name)!r}",
        "use a trusted archive with safe paths and members",
        code,
    )


def _name_parts(name: str) -> tuple[str, ...]:
    if "\x00" in name or "\\" in name:
        raise _security("tar-path-invalid", name)
    path = PurePosixPath(name)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise _security("tar-path-invalid", name)
    return tuple(part for part in path.parts if part not in {"", "."})


def _inside(dest: Path, path: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(dest)))
        return True
    except ValueError:
        return False


def _validate_members(members: list[tarfile.TarInfo], dest: Path, limits) -> None:  # type: ignore[no-untyped-def]
    max_members = int(limits.max_archive_members)
    if len(members) > max_members:
        raise SecurityError(
            "Archive contains too many members",
            "use an archive within the configured member limit",
            "archive-too-many-members",
        )
    for member in members:
        _name_parts(member.name)
        if member.issym() or member.islnk():
            target = Path(member.linkname)
            if member.issym():
                resolved = dest / PurePosixPath(member.name).parent / target
            else:
                resolved = dest / target
            if target.is_absolute() or not _inside(dest, resolved):
                raise _security("tar-link-escape", member.name)
        elif (
            member.ischr()
            or member.isblk()
            or member.isfifo()
            or (not member.isdir() and not member.isfile())
        ):
            raise _security("tar-special-member", member.name)


def _read_members(archive: tarfile.TarFile, limits) -> list[tarfile.TarInfo]:  # type: ignore[no-untyped-def]
    """Read only up to the configured member cap before rejecting a header bomb."""
    members: list[tarfile.TarInfo] = []
    maximum = int(limits.max_archive_members)
    for member in archive:
        members.append(member)
        if len(members) > maximum:
            raise SecurityError(
                "Archive contains too many members",
                "use an archive within the configured member limit",
                "archive-too-many-members",
            )
    return members


def _apply_data_filter(member: tarfile.TarInfo, dest: Path) -> tarfile.TarInfo:
    # Python 3.12's data_filter is an additional defense; explicit checks above
    # remain necessary for supported Python 3.11 and for the streaming caps.
    data_filter = getattr(tarfile, "data_filter", None)
    if data_filter is not None:
        try:
            filtered = data_filter(member, str(dest))
        except (tarfile.TarError, ValueError) as exc:
            raise _security("tar-path-invalid", member.name) from exc
        if filtered is None:
            raise _security("tar-path-invalid", member.name)
        if not isinstance(filtered, tarfile.TarInfo):
            raise _security("tar-path-invalid", member.name)
        return filtered
    return member


def extract_tar(src: Path, dest: Path, limits) -> list[Path]:  # type: ignore[no-untyped-def]
    """Extract a tar archive into *dest* after validating all members."""
    src, dest = Path(src), Path(dest)
    cap = int(limits.max_archive_total_mb) * 1024 * 1024
    temporary = dest.parent / f".{dest.name}.extract-{uuid.uuid4().hex}"
    temporary.mkdir(parents=True, mode=0o700)
    total = 0
    result: list[Path] = []
    try:
        with tarfile.open(src, mode="r:*") as archive:
            members = _read_members(archive, limits)
            _validate_members(members, temporary, limits)
        with tarfile.open(src, mode="r:*") as archive:
            for member in archive.getmembers():
                filtered = _apply_data_filter(member, temporary)
                parts = _name_parts(filtered.name)
                output = temporary.joinpath(*parts)
                if filtered.isdir():
                    output.mkdir(parents=True, exist_ok=True)
                    output.chmod(0o755)
                    continue
                if filtered.issym():
                    output.parent.mkdir(parents=True, exist_ok=True)
                    link_target = filtered.linkname
                    os.symlink(link_target, output)
                    continue
                if filtered.islnk():
                    output.parent.mkdir(parents=True, exist_ok=True)
                    target = temporary.joinpath(*_name_parts(filtered.linkname))
                    if not _inside(temporary, target):
                        raise _security("tar-link-escape", filtered.name)
                    os.link(target, output)
                    continue
                stream = archive.extractfile(filtered)
                if stream is None:
                    raise _security("tar-special-member", filtered.name)
                output.parent.mkdir(parents=True, exist_ok=True)
                with stream, output.open("wb") as file:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if len(chunk) > cap or total > cap:
                            raise SecurityError(
                                "Archive decompressed size exceeded the configured cap",
                                "use an archive within the configured size limit",
                                "archive-bomb",
                            )
                        file.write(chunk)
                    file.flush()
                    os.fsync(file.fileno())
                output.chmod(0o644)
                result.append(dest.joinpath(*parts))
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        temporary.chmod(0o755)
        os.replace(temporary, dest)
        return result
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def gunzip_file(src: Path, dest: Path, max_mb: int) -> Path:
    """Decompress one gzip member with a streaming output cap."""
    src, dest = Path(src), Path(dest)
    cap = int(max_mb) * 1024 * 1024
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + ".tmp")
    total = 0
    try:
        if temporary.exists():
            temporary.unlink()
        with gzip.open(src, "rb") as input_file, temporary.open("wb") as output:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > cap:
                    raise SecurityError(
                        "Gzip decompressed size exceeded the configured cap",
                        "use a gzip file within the configured size limit",
                        "archive-bomb",
                    )
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, dest)
        return dest
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def sniff_kind(path: Path) -> Kind:
    """Classify using magic bytes and a bounded decompression peek."""
    path = Path(path)
    with path.open("rb") as file:
        prefix = file.read(1024)
    if prefix.startswith(b"%PDF-"):
        return "pdf"
    if len(prefix) >= 262 and prefix[257:262] == b"ustar":
        return "tar"
    if prefix.startswith(b"\x1f\x8b"):
        try:
            decompressor = __import__("zlib").decompressobj(31)
            expanded = decompressor.decompress(prefix, 1024)
        except Exception:
            return "unknown"
        if len(expanded) >= 262 and expanded[257:262] == b"ustar":
            return "tar-gz"
        text = expanded.decode("utf-8", errors="ignore")
        if "\\documentclass" in text or "\\begin" in text:
            return "gzip-single"
        return "gzip-single"
    text = prefix.decode("utf-8", errors="ignore")
    printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
    if text and printable / len(text) >= 0.8 and ("\\documentclass" in text or "\\begin" in text):
        return "tex"
    return "unknown"
