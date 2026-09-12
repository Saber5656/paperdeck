"""arXiv metadata and artifact acquisition through :mod:`paperdeck.netgate`."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from ..errors import FetchError, InputError, SecurityError
from ..netgate import NetGate
from .cache import CacheManager
from .tarsafe import gunzip_file, sniff_kind

_ATOM = "http://www.w3.org/2005/Atom"
_ARXIV = "http://arxiv.org/schemas/atom"
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArxivMeta:
    id: str
    latest_version: int
    resolved_version: int
    title: str
    authors: list[str]
    abstract: str
    updated: str
    abs_url: str
    doi: str | None
    categories: list[str]


@dataclass(frozen=True)
class EprintArtifact:
    kind: str
    path: Path


@dataclass(frozen=True)
class HtmlArtifact:
    page_path: Path
    asset_map: dict[str, str]
    skipped_images: list[str]
    fetched_at: str


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def _version_from_id(value: str) -> tuple[str, int]:
    match = re.search(r"(v(\d+))$", value)
    if not match:
        return value, 1
    return value[: match.start()], int(match.group(2))


class ArxivClient:
    def __init__(self, netgate: NetGate, cache: CacheManager) -> None:
        self.netgate, self.cache = netgate, cache

    def _meta_key(self, arxiv_id: str, version: int | None) -> str:
        name = arxiv_id.replace("/", "--")
        folder = "latest-unknown" if version is None else str(version)
        return f"arxiv/{name}/{folder}/meta.xml"

    def _parse(self, payload: bytes, requested: int | None, arxiv_id: str) -> ArxivMeta:
        if re.search(rb"<!DOCTYPE|<!ENTITY", payload, flags=re.IGNORECASE):
            raise SecurityError(
                "XML DTD and entities are not permitted",
                "use an unmodified arXiv Atom response",
                "xml-dtd",
            )
        try:
            root = ElementTree.fromstring(payload)  # noqa: S314 - DTD/entity markers are rejected above
        except ElementTree.ParseError as exc:
            raise FetchError(
                "The arXiv metadata response was not valid XML",
                "retry the fetch or use a cached artifact",
                "metadata-invalid-xml",
            ) from exc
        entries = root.findall(f"{{{_ATOM}}}entry")
        if not entries:
            raise InputError(
                f"arXiv ID not found: {arxiv_id[:120]}",
                "check the identifier and try again",
                "arxiv-id-not-found",
            )
        entry = entries[0]
        title = _clean(entry.findtext(f"{{{_ATOM}}}title"))
        entry_id = _clean(entry.findtext(f"{{{_ATOM}}}id"))
        entry_value = entry_id
        for marker in ("/abs/", "/pdf/", "/html/"):
            if marker in entry_value:
                entry_value = entry_value.split(marker, 1)[1]
                break
        base_id, latest = _version_from_id(entry_value or arxiv_id)
        if title.lower() == "error" or not entry_id:
            raise InputError(
                f"arXiv ID not found: {arxiv_id[:120]}",
                "check the identifier and try again",
                "arxiv-id-not-found",
            )
        if requested is not None and requested > latest:
            raise InputError(
                f"arXiv version v{requested} does not exist for {arxiv_id[:120]}",
                "use a version listed by arXiv",
                "arxiv-version-not-found",
            )
        resolved = requested or latest
        authors = [
            _clean(item.findtext(f"{{{_ATOM}}}name"))
            for item in entry.findall(f"{{{_ATOM}}}author")
        ]
        links = entry.findall(f"{{{_ATOM}}}link")
        abs_url = next(
            (
                str(item.attrib.get("href"))
                for item in links
                if item.attrib.get("rel") in {"alternate", None} and item.attrib.get("href")
            ),
            f"https://arxiv.org/abs/{base_id}v{latest}",
        )
        doi_node = entry.find(f"{{{_ARXIV}}}doi")
        categories = [
            str(item.attrib.get("term"))
            for item in entry.findall(f"{{{_ATOM}}}category")
            if item.attrib.get("term")
        ]
        return ArxivMeta(
            base_id,
            latest,
            resolved,
            title,
            authors,
            _clean(entry.findtext(f"{{{_ATOM}}}summary")),
            _clean(entry.findtext(f"{{{_ATOM}}}updated")),
            abs_url,
            _clean(doi_node.text) or None if doi_node is not None else None,
            categories,
        )

    def metadata(self, arxiv_id: str, version: int | None) -> ArxivMeta:
        offline = bool(
            getattr(
                self.netgate,
                "offline",
                getattr(getattr(self.netgate, "settings", None), "offline", False),
            )
        )
        if version is not None:
            cached = self.cache.get(self._meta_key(arxiv_id, version))
            if cached is not None:
                return self._parse(cached.read_bytes(), version, arxiv_id)
        elif offline:
            versions = self.cache.versions(arxiv_id)
            if not versions:
                raise FetchError(
                    "Metadata is not cached in offline mode",
                    "run paperdeck fetch first, then retry without offline mode",
                    "offline",
                )
            chosen = versions[-1]
            cached = self.cache.get(self._meta_key(arxiv_id, chosen))
            if cached is None:
                raise FetchError(
                    "Metadata is not cached in offline mode",
                    "run paperdeck fetch first, then retry without offline mode",
                    "offline",
                )
            return self._parse(cached.read_bytes(), chosen, arxiv_id)

        url = "https://export.arxiv.org/api/query?id_list=" + quote(arxiv_id, safe="")
        try:
            response = self.netgate.client("arxiv").get(url)
            response.raise_for_status()
        except (FetchError, SecurityError):
            raise
        except Exception as exc:
            raise FetchError(
                "Could not fetch arXiv metadata",
                "check your network connection and retry",
                "network-error",
            ) from exc
        payload = response.content
        meta = self._parse(payload, version, arxiv_id)
        unknown_key = self._meta_key(arxiv_id, None)
        self.cache.put(unknown_key, payload)
        self.cache.promote(arxiv_id, meta.latest_version)
        if version is not None and version != meta.latest_version:
            # The Atom response remains useful for a requested historical version;
            # retain a copy in its deterministic version directory.
            self.cache.put(self._meta_key(arxiv_id, version), payload)
        return meta

    def _versioned(self, arxiv_id: str, version: int) -> str:
        return f"{arxiv_id}v{version}"

    def eprint(self, arxiv_id: str, version: int) -> EprintArtifact:
        for filename, kind in (
            ("source.tar.gz", "tar-gz"),
            ("source.tex", "tex"),
            ("source.pdf", "pdf-only"),
        ):
            found = self.cache.get(f"arxiv/{arxiv_id.replace('/', '--')}/{version}/{filename}")
            if found is not None:
                return EprintArtifact(kind, found)
        with tempfile.TemporaryDirectory(prefix="paperdeck-eprint-") as work:
            download = Path(work) / "eprint"
            self.netgate.download(
                f"https://export.arxiv.org/e-print/{self._versioned(arxiv_id, version)}",
                download,
                "arxiv",
            )
            kind = sniff_kind(download)
            if kind in {"tar", "tar-gz"}:
                destination = self.cache.put(
                    f"arxiv/{arxiv_id.replace('/', '--')}/{version}/source.tar.gz", download
                )
                return EprintArtifact("tar-gz", destination)
            if kind == "gzip-single":
                tex = Path(work) / "source.tex"
                gunzip_file(download, tex, int(self.netgate.settings.fetch.max_download_mb))
                destination = self.cache.put(
                    f"arxiv/{arxiv_id.replace('/', '--')}/{version}/source.tex", tex
                )
                return EprintArtifact("tex", destination)
            if kind == "pdf":
                destination = self.cache.put(
                    f"arxiv/{arxiv_id.replace('/', '--')}/{version}/source.pdf", download
                )
                return EprintArtifact("pdf-only", destination)
            raise FetchError(
                "The arXiv e-print format was not recognized",
                "try fetching the PDF or use a different engine",
                "eprint-unrecognized",
            )

    def pdf(self, arxiv_id: str, version: int) -> Path:
        key = f"arxiv/{arxiv_id.replace('/', '--')}/{version}/paper.pdf"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix="paperdeck-pdf-") as work:
            temporary = Path(work) / "paper.pdf"
            self.netgate.download(
                f"https://export.arxiv.org/pdf/{self._versioned(arxiv_id, version)}",
                temporary,
                "arxiv",
            )
            if sniff_kind(temporary) != "pdf":
                raise FetchError(
                    "The arXiv PDF response was not a PDF",
                    "retry the fetch or use the e-print source",
                    "pdf-unrecognized",
                )
            return self.cache.put(key, temporary)

    def html_page(self, arxiv_id: str, version: int) -> HtmlArtifact | None:
        prefix = f"arxiv/{arxiv_id.replace('/', '--')}/{version}/html"
        page_key = prefix + "/index.html"
        cached = self.cache.get(page_key)
        if cached is not None:
            sidecar = self.cache.get(prefix + "/asset-map.json")
            cached_asset_map: dict[str, str] = {}
            if sidecar is not None:
                try:
                    cached_asset_map = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    cached_asset_map = {}
            return HtmlArtifact(cached, cached_asset_map, [], "cached")
        page_url = ""
        payload: bytes | None = None
        with tempfile.TemporaryDirectory(prefix="paperdeck-html-") as work:
            for host in ("export.arxiv.org", "arxiv.org"):
                page_url = f"https://{host}/html/{self._versioned(arxiv_id, version)}"
                page_download = Path(work) / "index.html"
                try:
                    self.netgate.download(page_url, page_download, "arxiv")
                    payload = page_download.read_bytes()
                    break
                except FetchError as exc:
                    if exc.code in {"http-404", "http-405"}:
                        continue
                    raise
            if payload is None:
                return None
            page = self.cache.put(page_key, payload)
            soup = BeautifulSoup(payload, "html.parser")
            skipped: list[str] = []
            asset_map: dict[str, str] = {}
            all_images = soup.find_all("img")
            image_nodes = list(all_images[:200])
            for node in image_nodes:
                source = str(node.get("src") or "")
                parsed = urlparse(source)
                if not source or parsed.scheme or parsed.netloc:
                    skipped.append(source)
                    continue
                asset_url = urljoin(page_url, source)
                if urlparse(asset_url).hostname != urlparse(page_url).hostname:
                    skipped.append(source)
                    continue
                temporary = (
                    Path(work)
                    / hashlib.sha1(source.encode("utf-8"), usedforsecurity=False).hexdigest()
                )
                try:
                    self.netgate.download(asset_url, temporary, "arxiv")
                    data = temporary.read_bytes()
                    extension = self._image_extension(data)
                    if extension is None or extension == ".gif":
                        skipped.append(source)
                        continue
                    name = (
                        hashlib.sha1(source.encode("utf-8"), usedforsecurity=False).hexdigest()
                        + extension
                    )
                    self.cache.put(prefix + "/assets/" + name, data)
                    asset_map[source] = name
                except SecurityError:
                    raise
                except Exception:
                    skipped.append(source)
            self.cache.put(
                prefix + "/asset-map.json", json.dumps(asset_map, sort_keys=True).encode("utf-8")
            )
            skipped.extend(str(item.get("src") or "") for item in all_images[200:])
            return HtmlArtifact(page, asset_map, skipped, datetime.now(UTC).isoformat())

    @staticmethod
    def _image_extension(data: bytes) -> str | None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return ".gif"
        sample = data[:4096].lstrip()
        if sample.startswith(b"<?xml"):
            end = sample.find(b"?>")
            if end >= 0:
                sample = sample[end + 2 :].lstrip()
        if sample.startswith(b"<svg"):
            return ".svg"
        return None
