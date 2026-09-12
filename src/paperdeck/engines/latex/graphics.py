"""Safe LaTeX graphics resolution and asset conversion."""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from paperdeck.errors import SecurityError
from paperdeck.ir.model import Asset, AssetOrigin, Figure, Warning


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index : index + 2], "big")
        if (
            0xC0 <= marker <= 0xC3
            or 0xC5 <= marker <= 0xC7
            or 0xC9 <= marker <= 0xCB
            or 0xCD <= marker <= 0xCF
        ):
            if index + 7 <= len(data):
                return int.from_bytes(data[index + 5 : index + 7], "big"), int.from_bytes(
                    data[index + 3 : index + 5], "big"
                )
            break
        index += max(length, 2)
    return None


def _graphic_dirs(preamble: str, root: Path) -> list[Path]:
    match = re.search(r"\\graphicspath\s*\{((?:\{[^}]*\})+)\}", preamble)
    if not match:
        return [root]
    dirs = [root / item for item in re.findall(r"\{([^}]*)\}", match.group(1))]
    return dirs + [root]


def _resolve(root: Path, target: str, dirs: list[Path]) -> Path | None:
    names = (
        [target]
        if Path(target).suffix
        else [target + suffix for suffix in (".pdf", ".png", ".jpg", ".jpeg")]
    )
    for directory in dirs:
        for name in names:
            candidate = (directory / name).resolve(strict=False)
            if not candidate.is_relative_to(root.resolve()):
                raise SecurityError(
                    "graphics path escapes source root",
                    hint="Keep graphics inside the source tree.",
                    code="graphics-escape",
                )
            if candidate.is_file():
                return candidate
    return None


def _placeholder(figure: Figure, reason: str) -> Figure:
    return figure.model_copy(
        update={"asset_id": None, "alt_text": f"figure unavailable ({reason})"}
    )


def _replace_figure(items: list[Any], figure_id: str, replacement: Figure) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if isinstance(item, Figure) and item.id == figure_id:
            result.append(replacement)
        elif hasattr(item, "children"):
            result.append(
                item.model_copy(
                    update={"children": _replace_figure(item.children, figure_id, replacement)}
                )
            )
        elif hasattr(item, "content") and item.__class__.__name__ == "Quote":
            result.append(
                item.model_copy(
                    update={"content": _replace_figure(item.content, figure_id, replacement)}
                )
            )
        elif hasattr(item, "items"):
            new_items = [_replace_figure(group, figure_id, replacement) for group in item.items]
            result.append(item.model_copy(update={"items": new_items}))
        else:
            result.append(item)
    return result


def _asset(
    path: Path,
    root: Path,
    figure_id: str,
    data: bytes,
    width: int | None,
    height: int | None,
    engine: str = "latex",
) -> Asset:
    import base64

    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
        path.suffix.lower(), "image/png"
    )
    return Asset(
        id=figure_id,
        mime=mime,  # type: ignore[arg-type]
        data_b64=base64.b64encode(data).decode("ascii"),
        width_px=width,
        height_px=height,
        origin=AssetOrigin(engine=engine, source_path=str(path.relative_to(root))),
    )


def resolve_graphics(doc: Any, project: Any, limits: Any) -> tuple[dict[str, Asset], list[Warning]]:
    """Resolve mapped figure targets and mutate mapped figure asset references."""
    assets: dict[str, Asset] = {}
    warnings: list[Warning] = []
    dirs = _graphic_dirs(project.preamble, project.root)
    counter = 0

    def blocks(items: list[Any]) -> Iterator[Any]:
        for item in items:
            yield item
            if hasattr(item, "children"):
                yield from blocks(item.children)
            if hasattr(item, "content") and item.__class__.__name__ == "Quote":
                yield from blocks(item.content)
            if hasattr(item, "items"):
                for group in item.items:
                    yield from blocks(group)

    for figure in (item for item in blocks(doc.body) if isinstance(item, Figure)):
        target = doc.image_targets.get(figure.id, "")
        try:
            path = _resolve(project.root, target, dirs)
        except SecurityError:
            raise
        if path is None:
            warnings.append(
                Warning(
                    code="figure-format-unsupported",
                    message="figure target is missing",
                    where=target,
                )
            )
            doc.body = _replace_figure(doc.body, figure.id, _placeholder(figure, "missing"))
            continue
        suffix = path.suffix.lower()
        if suffix == ".eps":
            warnings.append(
                Warning(
                    code="figure-eps-unsupported",
                    message="EPS figures are unsupported",
                    where=target,
                )
            )
            doc.body = _replace_figure(doc.body, figure.id, _placeholder(figure, "eps"))
            continue
        if suffix in {".png", ".jpg", ".jpeg"}:
            data = path.read_bytes()
            dims = png_dimensions(data) if suffix == ".png" else jpeg_dimensions(data)
            valid_magic = dims is not None
            if not valid_magic:
                raise SecurityError(
                    "graphic magic bytes do not match extension",
                    hint="Replace the malformed image.",
                    code="asset-magic-mismatch",
                )
            if path.stat().st_size > 10 * 1024 * 1024:
                warnings.append(
                    Warning(
                        code="figure-oversize-bytes", message="figure exceeds 10 MB", where=target
                    )
                )
                doc.body = _replace_figure(doc.body, figure.id, _placeholder(figure, "oversize"))
                continue
            if dims is None:
                continue
            if max(dims) > 4096:
                warnings.append(
                    Warning(
                        code="figure-too-large",
                        message="figure dimensions exceed 4096 px",
                        where=target,
                    )
                )
                doc.body = _replace_figure(doc.body, figure.id, _placeholder(figure, "dimensions"))
                continue
        elif suffix == ".pdf":
            try:
                import pypdfium2 as pdfium  # type: ignore[import-untyped]

                with pdfium.PdfDocument(str(path)) as pdf:
                    if len(pdf) > 1:
                        warnings.append(
                            Warning(
                                code="figure-pdf-multipage",
                                message="only page 1 of figure PDF used",
                                where=target,
                            )
                        )
                    page = pdf[0]
                    try:
                        width, height = page.get_size()
                        scale = min(2.0, 2000 / max(width, height))
                        bitmap = page.render(scale=scale)
                        image = bitmap.to_pil()
                        stream = io.BytesIO()
                        image.save(stream, format="PNG")
                        data = stream.getvalue()
                        dims = (image.width, image.height)
                    finally:
                        page.close()
            except Exception as exc:
                warnings.append(
                    Warning(
                        code="figure-pdf-failed",
                        message=f"PDF figure render failed: {exc}",
                        where=target,
                    )
                )
                continue
            if len(data) > 10 * 1024 * 1024:
                warnings.append(
                    Warning(
                        code="figure-oversize-bytes", message="figure exceeds 10 MB", where=target
                    )
                )
                doc.body = _replace_figure(doc.body, figure.id, _placeholder(figure, "oversize"))
                continue
        else:
            warnings.append(
                Warning(
                    code="figure-format-unsupported",
                    message="figure format unsupported",
                    where=target,
                )
            )
            doc.body = _replace_figure(doc.body, figure.id, _placeholder(figure, "format"))
            continue
        counter += 1
        asset_id = f"asset-{counter}"
        assets[asset_id] = _asset(path, project.root, asset_id, data, dims[0], dims[1])
        doc.body = _replace_figure(
            doc.body, figure.id, figure.model_copy(update={"asset_id": asset_id})
        )
    return assets, warnings
