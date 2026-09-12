"""Deterministic local Chat Completions server for security/E2E tests."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import httpx

ResponsePlan = Callable[
    [dict[str, Any]],
    tuple[int, dict[str, Any] | str] | tuple[int, dict[str, Any] | str, dict[str, str]],
]


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        server = self.server
        assert isinstance(server, _FakeServer)
        auth = self.headers.get("Authorization", "")
        if server.require_auth and not re.fullmatch(r"Bearer [^\s]+", auth):
            self._send(401, {"error": "authorization required"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length))
        except (ValueError, TypeError):
            self._send(400, {"error": "invalid request"})
            return
        server.requests.append(request)
        response = server.plan(request)
        status, payload = response[:2]
        headers = response[2] if len(response) == 3 else {}
        self._send(status, payload, headers)

    def _send(
        self,
        status: int,
        payload: dict[str, Any] | str,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


class _FakeServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], require_auth: bool, plan: ResponsePlan):
        super().__init__(address, _Handler)
        self.require_auth = require_auth
        self.plan = plan
        self.requests: list[dict[str, Any]] = []


class FakeLLM:
    def __init__(self, *, require_auth: bool = True, plan: ResponsePlan | None = None):
        self.require_auth = require_auth
        self.plan = plan or self.default_plan
        self.server: _FakeServer | None = None
        self.thread: Thread | None = None

    @property
    def base_url(self) -> str:
        if self.server is None:
            raise RuntimeError("FakeLLM is not started")
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.server.requests if self.server else []

    def start(self) -> FakeLLM:
        self.server = _FakeServer(("127.0.0.1", 0), self.require_auth, self.plan)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None

    def __enter__(self) -> FakeLLM:
        return self.start()

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def default_plan(request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        response_format = request.get("response_format", {})
        schema = response_format.get("json_schema", {}) if isinstance(response_format, dict) else {}
        name = schema.get("name", "") if isinstance(schema, dict) else ""
        if name == "pdf_segment":
            blocks: list[dict[str, Any]] = []
            for line in "\n".join(
                str(message.get("content", "")) for message in request.get("messages", [])
            ).splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if (
                    not isinstance(item, dict)
                    or not item.get("id")
                    or str(item["id"]).startswith("ctx-")
                ):
                    continue
                text = str(item.get("text", ""))
                role = "paragraph"
                output: dict[str, Any] = {"id": item["id"], "role": role}
                lowered = text.lower()
                if "abstract" in lowered:
                    output["role"] = "abstract"
                elif lowered.startswith("figure"):
                    output.update(role="figure_caption", number_text="1")
                elif lowered.startswith("references"):
                    output.update(role="heading", level=1)
                elif text.startswith("[1]"):
                    output.update(role="bib_entry", number_text="1")
                elif "introduction" in lowered:
                    output.update(role="heading", level=1)
                elif text.strip() == "x = y":
                    output.update(role="display_equation", number_text="1")
                elif text.startswith("An end"):
                    output["role"] = "title"
                elif text == "Alice Example":
                    output["role"] = "author_line"
                blocks.append(output)
            content = json.dumps({"blocks": blocks, "section_order": [b["id"] for b in blocks]})
            return 200, {
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 20},
            }
        if name == "pdf_equation_latex":
            content = {"latex": "x = y", "confidence": 0.5}
        elif name == "pdf_bib":
            content = {"entries": [{"number": "1", "text": "Example reference", "urls": []}]}
        elif name == "pdf_cite_map":
            content = {"mappings": []}
        else:
            content = {}
        return 200, {
            "choices": [{"message": {"content": json.dumps(content)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 20},
        }


def assert_auth(server: FakeLLM, *, key: str | None) -> int:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    response = httpx.post(server.base_url + "/chat/completions", headers=headers, json={})
    return response.status_code
