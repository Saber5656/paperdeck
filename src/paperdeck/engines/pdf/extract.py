"""Bounded pypdfium2 PDF extraction and Pillow-free bitmap cropping."""

from __future__ import annotations

import struct
import unicodedata
import zlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from ...errors import ConversionError, InputError


@dataclass(frozen=True)
class Char:
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float


@dataclass(frozen=True)
class PageChars:
    page: int
    chars: list[Char]
    width: float
    height: float


def encode_png_rgb(width: int, height: int, pixels: bytes) -> bytes:
    if width < 1 or height < 1 or len(pixels) != width * height * 3:
        raise ValueError("invalid RGB bitmap")
    raw = b"".join(b"\0" + pixels[row * width * 3 : (row + 1) * width * 3] for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


class PageBitmap:
    def __init__(self, bitmap: Any, width: int, height: int, scale: float) -> None:
        self._bitmap = bitmap
        self.width = width
        self.height = height
        self.scale = scale
        self._closed = False

    def _rgb(self) -> bytes:
        bitmap = self._bitmap
        if hasattr(bitmap, "to_numpy"):
            try:
                arr = bitmap.to_numpy()
                channels = int(getattr(arr, "shape", [0, 0, 3])[-1])
                return (
                    bytes(arr[:, :, :3].astype("uint8").tobytes())
                    if channels >= 3
                    else bytes(arr.tobytes())
                )
            except ImportError:
                # numpy is optional; use pdfium's contiguous buffer below.
                pass
        raw = bytes(getattr(bitmap, "buffer", bitmap))
        channels = int(getattr(bitmap, "n_channels", 4) or 4)
        if channels == 3:
            return raw[: self.width * self.height * 3]
        # PDFium commonly returns BGRA; discard alpha and swap blue/red.
        out = bytearray(self.width * self.height * 3)
        for i in range(min(self.width * self.height, len(raw) // channels)):
            src = i * channels
            dst = i * 3
            out[dst : dst + 3] = bytes((raw[src + 2], raw[src + 1], raw[src]))
        return bytes(out)

    def crop_png(self, bbox_points: tuple[float, float, float, float], pad_pt: float = 6) -> bytes:
        left, bottom, right, top = bbox_points
        left = max(0.0, left - pad_pt) * self.scale
        right = min(self.width / self.scale, right + pad_pt) * self.scale
        # The only PDF-to-raster y-axis conversion in the engine.
        top_px = max(0.0, (self.height / self.scale - top - pad_pt) * self.scale)
        bottom_px = min(
            float(self.height), (self.height / self.scale - bottom + pad_pt) * self.scale
        )
        x0, x1 = max(0, int(left)), min(self.width, int(right + 0.999))
        y0, y1 = max(0, int(top_px)), min(self.height, int(bottom_px + 0.999))
        if x1 <= x0 or y1 <= y0:
            raise ValueError("zero-area crop")
        rgb = self._rgb()
        cropped = bytearray((x1 - x0) * (y1 - y0) * 3)
        for row in range(y0, y1):
            src = (row * self.width + x0) * 3
            dst = ((row - y0) * (x1 - x0)) * 3
            cropped[dst : dst + (x1 - x0) * 3] = rgb[src : src + (x1 - x0) * 3]
        return encode_png_rgb(x1 - x0, y1 - y0, bytes(cropped))

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            close = getattr(self._bitmap, "close", None)
            if close:
                close()

    def __enter__(self) -> PageBitmap:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class PdfDoc:
    def __init__(self, path: Path, limits: Any) -> None:
        self.path = Path(path)
        self.limits = limits
        self._document: Any = None
        self._pages: OrderedDict[tuple[int, float], PageBitmap] = OrderedDict()
        self._char_pages: dict[int, PageChars] = {}
        self.warnings: list[str] = []
        self._failed_pages = 0
        try:
            self._document = pdfium.PdfDocument(str(self.path))
        except Exception as exc:
            detail = str(exc).lower()
            code = (
                "pdf-encrypted"
                if any(word in detail for word in ("password", "encrypt", "security"))
                else "pdf-unreadable"
            )
            hint = (
                "Provide an unencrypted PDF."
                if code == "pdf-encrypted"
                else "Check that the PDF is complete and readable."
            )
            raise InputError("Unable to open PDF", hint, code) from exc
        if self.page_count > int(limits.max_pdf_pages):
            self.close()
            raise InputError(
                "PDF has too many pages",
                "Reduce the PDF or increase max_pdf_pages.",
                "pdf-too-many-pages",
            )

    @property
    def page_count(self) -> int:
        return len(self._document)

    def page_size(self, page_i: int) -> tuple[float, float]:
        page = self._document.get_page(page_i)
        try:
            return tuple(float(x) for x in page.get_size())  # type: ignore[return-value]
        finally:
            close = getattr(page, "close", None)
            if close:
                close()

    def chars(self, page_i: int) -> list[Char]:
        if page_i in self._char_pages:
            return list(self._char_pages[page_i].chars)
        try:
            page = self._document.get_page(page_i)
            textpage = page.get_textpage()
            count = int(textpage.count_chars())
            chars: list[Char] = []
            for idx in range(count):
                text = textpage.get_text_range(idx, 1)
                if not text:
                    continue
                box = tuple(float(value) for value in textpage.get_charbox(idx))
                if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
                    continue
                chars.append(
                    Char(unicodedata.normalize("NFC", str(text)), box, max(0.1, box[3] - box[1]))
                )
            width, height = self.page_size(page_i)
            self._char_pages[page_i] = PageChars(page_i, chars, width, height)
            close = getattr(textpage, "close", None)
            if close:
                close()
            close = getattr(page, "close", None)
            if close:
                close()
            return list(chars)
        except Exception as exc:
            self._failed_pages += 1
            warning = f"pdf-page-failed:{page_i}"
            self.warnings.append(warning)
            if self._failed_pages / max(1, self.page_count) > 0.10:
                raise ConversionError(
                    "PDF contains too many unreadable pages",
                    "Repair the PDF and retry.",
                    "pdf-too-broken",
                ) from exc
            return []

    def page_chars(self, page_i: int) -> PageChars:
        self.chars(page_i)
        return self._char_pages.get(page_i, PageChars(page_i, [], *self.page_size(page_i)))

    def bitmap(self, page_i: int, scale: float = 2.0) -> PageBitmap:
        cache_key = (page_i, scale)
        if cache_key in self._pages:
            self._pages.move_to_end(cache_key)
            return self._pages[cache_key]
        page = self._document.get_page(page_i)
        try:
            bitmap = page.render(scale=scale, rev_byteorder=True)
            size = self.page_size(page_i)
            width = int(round(size[0] * scale))
            height = int(round(size[1] * scale))
            result = PageBitmap(bitmap, width, height, scale)
            self._pages[cache_key] = result
            while len(self._pages) > 8:
                _, old = self._pages.popitem(last=False)
                old.close()
            return result
        finally:
            close = getattr(page, "close", None)
            if close:
                close()

    def close(self) -> None:
        for bitmap in self._pages.values():
            bitmap.close()
        self._pages.clear()
        if self._document is not None:
            close = getattr(self._document, "close", None)
            if close:
                close()
            self._document = None

    def __enter__(self) -> PdfDoc:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def open_pdf(path: Path, limits: Any) -> PdfDoc:
    try:
        size = Path(path).stat().st_size
    except OSError as exc:
        raise InputError("PDF cannot be read", "Check the input path.", "pdf-unreadable") from exc
    if size > int(limits.max_input_mb) * 1024 * 1024:
        raise InputError(
            "PDF exceeds input size limit",
            "Reduce the PDF or increase max_input_mb.",
            "pdf-too-large",
        )
    return PdfDoc(Path(path), limits)


__all__ = ["Char", "PageBitmap", "PageChars", "PdfDoc", "encode_png_rgb", "open_pdf"]
