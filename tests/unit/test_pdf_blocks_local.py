from types import SimpleNamespace

from paperdeck.engines.pdf.blocks import build_blocks


def chars(text: str, y: float = 100, start: float = 10, size: float = 10):
    return [
        SimpleNamespace(
            text=c,
            bbox=(start + i * size * 0.6, y, start + i * size * 0.6 + size * 0.45, y + size),
            font_size=size,
        )
        for i, c in enumerate(text)
    ]


def test_blocks_are_deterministic_and_repair_space_boundary() -> None:
    page = SimpleNamespace(page=0, width=600, height=800, chars=chars("ab") + chars("next", 70))
    first = build_blocks([page])
    shuffled = SimpleNamespace(page=0, width=600, height=800, chars=list(reversed(page.chars)))
    second = build_blocks([shuffled])
    assert [(b.text, b.bbox) for b in first] == [(b.text, b.bbox) for b in second]
    assert first[0].text == "ab"


def test_repeated_runner_is_removed_only_with_four_pages() -> None:
    pages = [
        SimpleNamespace(
            page=i, width=600, height=800, chars=chars("Page 1", 780) + chars(f"body{i}", 100)
        )
        for i in range(6)
    ]
    blocks = build_blocks(pages)
    assert all("Page" not in block.text for block in blocks)
