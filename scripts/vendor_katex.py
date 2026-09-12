"""Vendor KaTeX reproducibly from two official distribution channels.

Bootstrap: GitHub's archive digest and npm's dist.integrity authenticate each archive;
compare the bytes of every selected JS/CSS/font/license in both (the archives themselves
have different packaging). Updating these constants requires repeating both checks.
No archive member is extracted to disk; only explicitly selected regular files are written.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

KATEX_VERSION = "0.18.7"
SOURCE_URL = f"https://github.com/KaTeX/KaTeX/releases/download/v{KATEX_VERSION}/katex.tar.gz"
EXPECTED_ARCHIVE_SHA256 = "ea488c6a60ca97b9c92c010e7cd400f13f39fb262d8d506bd85bba3e528a7b53"
NPM_INTEGRITY = (
    "h+UCwkZ+4Jz8WQ7MLGfj7UVFrRCizGb912fwF4luGdYsC5paYG1vx+jy+KRcC/XkpjGva/P7nAWuxNnPzRvzHw=="
)
ROOT = Path(__file__).resolve().parents[1] / "src/paperdeck/render/assets/vendor/katex"


def selected(name: str) -> str | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive path")
    parts = path.parts
    if parts and parts[0] in {"katex", "package"}:
        parts = parts[1:]
    if parts and parts[0] == "dist":
        parts = parts[1:]
    rel = "/".join(parts)
    if rel in {"katex.min.js", "katex.min.css", "LICENSE"}:
        return rel
    if len(parts) == 2 and parts[0] == "fonts" and parts[1].endswith(".woff2"):
        return rel
    return None


def unpack(data: bytes, expected_sha256: str) -> dict[str, bytes]:
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Archive checksum mismatch")
    output = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            rel = selected(member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("Unsafe archive member")
            if rel and member.isfile():
                if rel in output or member.size > 10_000_000:
                    raise ValueError("Duplicate or oversized archive member")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Missing member data")
                output[rel] = stream.read()
    return output


def verify_vendored(root: Path) -> list[str]:
    try:
        manifest = json.loads((root / "MANIFEST.json").read_text())
        files = manifest["files"]
        failures = []
        for name, checksum in files.items():
            if selected(name) != name:
                failures.append(name)
                continue
            path = root / name
            if (
                path.is_symlink()
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != checksum
            ):
                failures.append(name)
        for required in ("katex.min.js", "katex.min.css", "LICENSE"):
            if required not in files:
                failures.append(required)
        if not any(name.startswith("fonts/") for name in files):
            failures.append("fonts")
        return sorted(set(failures))
    except (OSError, ValueError, KeyError, TypeError):
        return ["MANIFEST.json"]


def download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("HTTPS required")
    with urlopen(url, timeout=120) as response:  # noqa: S310 -- fixed HTTPS release URLs
        return response.read(20_000_001)


def main() -> None:
    archive = download(SOURCE_URL)
    files = unpack(archive, EXPECTED_ARCHIVE_SHA256)
    npm = download(f"https://registry.npmjs.org/katex/-/katex-{KATEX_VERSION}.tgz")
    if base64.b64encode(hashlib.sha512(npm).digest()).decode() != NPM_INTEGRITY:
        raise ValueError("npm integrity mismatch")
    npm_files = unpack(npm, hashlib.sha256(npm).hexdigest())
    # The release archive omits LICENSE; compare npm's license with the tagged source.
    files["LICENSE"] = download(
        f"https://raw.githubusercontent.com/KaTeX/KaTeX/v{KATEX_VERSION}/LICENSE"
    )
    if files != npm_files:
        raise ValueError("GitHub/npm distribution contents differ")
    for name, data in files.items():
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = dict(
        version=KATEX_VERSION,
        source_url=SOURCE_URL,
        files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        generated_by="scripts/vendor_katex.py",
    )
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print(f"Vendored KaTeX {KATEX_VERSION}: {len(files)} verified files")


if __name__ == "__main__":
    main()
