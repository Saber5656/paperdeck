"""Deterministic PDF character clustering; intentionally independent of pdfium."""
# The local flush closure intentionally captures the per-page accumulator.
# ruff: noqa: B023

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RawBlock:
    id: str
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    font_size_median: float
    line_count: int
    column: int = 0
    line_height_median: float = 0.0


@dataclass
class _Line:
    chars: list[Any]
    bbox: tuple[float, float, float, float]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def text(self) -> str:
        ordered = sorted(self.chars, key=lambda c: (float(c.bbox[0]), float(c.bbox[1])))
        out = ""
        previous: Any | None = None
        for char in ordered:
            if previous is not None:
                gap = float(char.bbox[0]) - float(previous.bbox[2])
                if gap > 0.35 * max(float(previous.font_size), float(char.font_size)):
                    out += " "
            out += str(char.text)
            previous = char
        return " ".join(unicodedata.normalize("NFC", out).split())

    @property
    def font_size(self) -> float:
        return statistics.median(float(c.font_size) for c in self.chars)


def _overlap_ratio(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    overlap = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap / max(1e-9, min(a[3] - a[1], b[3] - b[1]))


def chars_to_lines(chars: list[Any]) -> list[_Line]:
    lines: list[_Line] = []
    for char in sorted(
        chars, key=lambda c: (-float(c.bbox[3]), float(c.bbox[0]), float(c.bbox[1]))
    ):
        candidate = next(
            (line for line in lines if _overlap_ratio(line.bbox, char.bbox) >= 0.5), None
        )
        if candidate is None:
            candidate = _Line([], tuple(float(x) for x in char.bbox[:4]))  # type: ignore[arg-type]
            lines.append(candidate)
        candidate.chars.append(char)
        candidate.bbox = (
            min(candidate.bbox[0], char.bbox[0]),
            min(candidate.bbox[1], char.bbox[1]),
            max(candidate.bbox[2], char.bbox[2]),
            max(candidate.bbox[3], char.bbox[3]),
        )
    return sorted(lines, key=lambda line: (-line.bbox[3], line.bbox[0]))


def detect_columns(lines: list[_Line], page_width: float) -> tuple[list[list[_Line]], str | None]:
    if len(lines) < 20 or page_width <= 0:
        return [sorted(lines, key=lambda x: (-x.bbox[3], x.bbox[0]))], None
    bins = [0] * max(1, int(page_width / 8) + 1)
    for line in lines:
        lo = max(0, int(line.bbox[0] / 8))
        hi = min(len(bins) - 1, int(line.bbox[2] / 8))
        for idx in range(lo, hi + 1):
            bins[idx] += 1
    low = [count <= max(1, int(len(lines) * 0.02)) for count in bins]
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for idx, is_low in enumerate(low + [False]):
        if is_low and start is None:
            start = idx
        elif not is_low and start is not None:
            if (idx - start) * 8 >= 24:
                runs.append((start, idx - 1))
            start = None
    central = [
        run for run in runs if page_width * 0.30 <= (run[0] + run[1] + 1) * 4 <= page_width * 0.70
    ]
    if not central:
        return [sorted(lines, key=lambda x: (-x.bbox[3], x.bbox[0]))], None
    valley = (central[0][0] + central[0][1] + 1) * 4
    left = [line for line in lines if line.bbox[2] <= valley]
    right = [line for line in lines if line.bbox[0] >= valley]
    side = len(left) + len(right)
    if side / len(lines) < 0.60:
        return [sorted(lines, key=lambda x: (-x.bbox[3], x.bbox[0]))], None
    return [sorted(left, key=lambda x: -x.bbox[3]), sorted(right, key=lambda x: -x.bbox[3])], None


def _norm_runner(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.split()).casefold())


def strip_repeated(
    pages: list[Any], lines_by_page: list[list[_Line]]
) -> tuple[list[list[_Line]], list[str]]:
    if len(pages) < 4:
        return lines_by_page, []
    candidates: dict[tuple[str, int], set[int]] = {}
    for page_idx, lines in enumerate(lines_by_page):
        for line in lines:
            band = int(round(line.bbox[1] / 6))
            candidates.setdefault((_norm_runner(line.text), band), set()).add(page_idx)
    repeated = {key for key, seen in candidates.items() if len(seen) >= len(pages) * 0.60}
    dropped = 0
    result: list[list[_Line]] = []
    for lines in lines_by_page:
        kept: list[_Line] = []
        for line in lines:
            key = (_norm_runner(line.text), int(round(line.bbox[1] / 6)))
            if key in repeated:
                dropped += 1
            else:
                kept.append(line)
        result.append(kept)
    return result, ([f"pdf-runners-stripped:{dropped}"] if dropped else [])


def build_blocks(pages: list[Any]) -> list[RawBlock]:
    line_lists = [chars_to_lines(list(getattr(page, "chars", page))) for page in pages]
    line_lists, warnings = strip_repeated(pages, line_lists)
    blocks: list[RawBlock] = []
    for page, lines in zip(pages, line_lists, strict=True):
        page_idx = int(getattr(page, "page", len(blocks)))
        width = float(getattr(page, "width", max((line.bbox[2] for line in lines), default=0)))
        columns, _ = detect_columns(lines, width)
        ordered_lines = [line for col in columns for line in col]
        median_height = (
            statistics.median([line.height for line in ordered_lines]) if ordered_lines else 10.0
        )
        current: list[_Line] = []
        page_blocks: list[RawBlock] = []

        def flush() -> None:  # noqa: B023
            if not current:
                return
            chars = [char for line in current for char in line.chars]
            bbox = (
                min(line.bbox[0] for line in current),
                min(line.bbox[1] for line in current),
                max(line.bbox[2] for line in current),
                max(line.bbox[3] for line in current),
            )
            text = "\n".join(line.text for line in current if line.text)
            if text:
                page_blocks.append(
                    RawBlock(
                        "",
                        page_idx,
                        bbox,
                        text,
                        statistics.median(float(c.font_size) for c in chars),
                        len(current),
                        0,
                        median_height,
                    )
                )
            current.clear()

        previous: _Line | None = None
        for line in ordered_lines:
            if previous is not None:
                gap = previous.bbox[1] - line.bbox[3]
                jump = abs(line.font_size - previous.font_size) > 0.25 * max(
                    line.font_size, previous.font_size
                )
                if gap > 1.8 * median_height or jump:
                    flush()
            current.append(line)
            previous = line
        flush()
        for idx, block in enumerate(page_blocks):
            blocks.append(
                RawBlock(
                    f"b{page_idx}-{idx}",
                    block.page,
                    block.bbox,
                    block.text,
                    block.font_size_median,
                    block.line_count,
                    block.column,
                    block.line_height_median,
                )
            )
    return blocks


__all__ = ["RawBlock", "build_blocks", "chars_to_lines", "detect_columns", "strip_repeated"]
