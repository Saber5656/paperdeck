"""Extract safe, simple macro definitions from a comment-free preamble."""

from __future__ import annotations

import re

from paperdeck.engines.latex.refs import read_group
from paperdeck.ir.model import Warning

_COMMAND = re.compile(r"\\(newcommand|renewcommand|providecommand|DeclareMathOperator|def)\*?")
_NAME = re.compile(r"\\[A-Za-z][A-Za-z0-9]*$")
_UNSAFE = re.compile(r"\\(?:if|csname|expandafter|futurelet|catcode)")


def _warning(code: str, message: str) -> Warning:
    return Warning(code=code, message=message)


def extract_macros(preamble: str) -> tuple[dict[str, str], list[Warning]]:
    macros: dict[str, str] = {}
    warnings: list[Warning] = []
    nested_names: set[str] = set()
    for match in _COMMAND.finditer(preamble):
        command = match.group(1)
        starred = (
            preamble[match.start() + len(match.group(0)) - 1 : match.start() + len(match.group(0))]
            == "*"
        )
        index = match.end()
        while index < len(preamble) and preamble[index].isspace():
            index += 1
        name: str | None = None
        body: str | None = None
        if command == "def":
            if index >= len(preamble) or preamble[index] != "\\":
                continue
            name_match = re.match(r"\\[A-Za-z][A-Za-z0-9]*", preamble[index:])
            if name_match is None:
                continue
            name = name_match.group(0)
            index += len(name)
            while index < len(preamble) and preamble[index].isspace():
                index += 1
            while index < len(preamble) and preamble[index] == "#":
                if index + 1 >= len(preamble) or not preamble[index + 1].isdigit():
                    break
                index += 2
            while index < len(preamble) and preamble[index].isspace():
                index += 1
            body, _ = read_group(preamble, index)
        else:
            name_group, index = read_group(preamble, index)
            if name_group is None:
                continue
            name = name_group.strip()
            if command == "DeclareMathOperator":
                body, _ = read_group(preamble, index)
                if body is not None:
                    body = f"\\operatorname{'*' if starred else ''}{{{body}}}"
            else:
                while index < len(preamble) and preamble[index].isspace():
                    index += 1
                arg_count: str | None = None
                if index < len(preamble) and preamble[index] == "[":
                    end = preamble.find("]", index + 1)
                    if end < 0:
                        continue
                    arg_count = preamble[index + 1 : end]
                    index = end + 1
                    while index < len(preamble) and preamble[index].isspace():
                        index += 1
                    if index < len(preamble) and preamble[index] == "[":
                        warnings.append(
                            _warning(
                                f"macro-optional-arg:{name}",
                                "optional macro arguments are unsupported",
                            )
                        )
                        continue
                body, _ = read_group(preamble, index)
                _ = arg_count
        if name is None or body is None:
            continue
        if "@" in name:
            warnings.append(_warning(f"macro-internal:{name}", "internal macro skipped"))
            continue
        if not _NAME.fullmatch(name):
            continue
        if len(body) > 2000:
            warnings.append(
                _warning(f"macro-too-large:{name}", "macro body exceeds 2000 characters")
            )
            continue
        if _UNSAFE.search(body) or re.search(
            r"\\(?:newcommand|renewcommand|providecommand|def)", body
        ):
            nested_names.update(
                re.findall(
                    r"\\(?:newcommand|renewcommand|providecommand)\s*\{(\\[A-Za-z][A-Za-z0-9]*)\}",
                    body,
                )
            )
            warnings.append(_warning(f"macro-unsafe:{name}", "unsafe or nested macro skipped"))
            continue
        if len(macros) >= 500 and name not in macros:
            warnings.append(_warning("macro-cap", "macro limit of 500 reached"))
            break
        if name in macros and command == "providecommand":
            continue
        if name in macros and command in {"newcommand", "def"}:
            warnings.append(_warning(f"macro-redefined:{name}", "macro redefined"))
        macros[name] = body
    return {name: body for name, body in macros.items() if name not in nested_names}, warnings
