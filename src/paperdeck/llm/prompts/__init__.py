"""Load reviewed prompt templates without permitting accidental slot omission."""

from __future__ import annotations

import importlib.resources
import string


def load_prompt(name: str, **slots: object) -> str:
    filename = name if name.endswith(".md") else f"{name}.md"
    try:
        template = (
            importlib.resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise ValueError(f"unknown prompt: {name}") from exc
    fields = {
        field_name for _, field_name, _, _ in string.Formatter().parse(template) if field_name
    }
    missing = fields - slots.keys()
    unknown = slots.keys() - fields
    if missing:
        raise ValueError(f"missing prompt slot: {sorted(missing)[0]}")
    if unknown:
        raise ValueError(f"unknown prompt slot: {sorted(unknown)[0]}")
    return template.format(**slots)


__all__ = ["load_prompt"]
