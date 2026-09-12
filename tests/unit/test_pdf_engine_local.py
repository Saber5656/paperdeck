import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from reportlab.pdfgen import canvas

from paperdeck.config import load_settings
from paperdeck.engines import EngineContext
from paperdeck.engines.pdf.engine import PdfEngine
from paperdeck.errors import ConversionError
from paperdeck.input.cache import CacheManager
from paperdeck.input.resolver import InputSpec


class FakeChatHandler(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):  # noqa: N802
        type(self).calls += 1
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        content = "\n".join(str(message.get("content", "")) for message in request["messages"])
        ids = list(dict.fromkeys(re.findall(r'"id":\s*"(b[^" ]+)"', content)))
        ids = [item for item in ids if not item.startswith("ctx-")]
        payload = {
            "blocks": [{"id": item, "role": "paragraph"} for item in ids],
            "section_order": ids,
        }
        body = json.dumps(
            {
                "choices": [{"message": {"content": json.dumps(payload)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def _fixture(path: Path) -> None:
    doc = canvas.Canvas(str(path), pagesize=(612, 792))
    doc.setFont("Helvetica", 14)
    doc.drawString(72, 720, "An end to end PDF")
    doc.setFont("Helvetica", 10)
    doc.drawString(72, 680, "A paragraph sent through the local fake model.")
    doc.showPage()
    doc.save()


def test_pdf_engine_runs_through_local_fake_chat_and_validates_ir(tmp_path: Path) -> None:
    FakeChatHandler.calls = 0
    server = HTTPServer(("localhost", 0), FakeChatHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pdf = tmp_path / "paper.pdf"
        _fixture(pdf)
        settings = load_settings(
            None, {"llm.base_url": f"http://localhost:{server.server_port}/v1"}
        )
        spec = InputSpec("pdf-local", path=pdf, original=str(pdf))
        context = EngineContext(
            spec, settings, CacheManager(tmp_path / "paperdeck"), tmp_path, lambda _: True
        )
        document = PdfEngine().convert(context)
        assert FakeChatHandler.calls == 1
        assert document.body
        assert document.provenance.llm is not None
        assert document.provenance.llm.calls == 1
        assert context.run_metrics["calls"] == 1
        assert context.run_metrics["actual_usd"] is not None
        assert set(context.run_metrics) == {
            "calls",
            "cache_hits",
            "tokens_in",
            "tokens_out",
            "estimated_usd",
            "actual_usd",
        }
    finally:
        server.shutdown()


def test_pdf_engine_declined_cost_does_not_call_model(tmp_path: Path) -> None:
    FakeChatHandler.calls = 0
    server = HTTPServer(("localhost", 0), FakeChatHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        pdf = tmp_path / "paper.pdf"
        _fixture(pdf)
        settings = load_settings(
            None, {"llm.base_url": f"http://localhost:{server.server_port}/v1"}
        )
        spec = InputSpec("pdf-local", path=pdf, original=str(pdf))
        context = EngineContext(
            spec, settings, CacheManager(tmp_path / "paperdeck"), tmp_path, lambda _: False
        )
        try:
            PdfEngine().convert(context)
        except ConversionError as exc:
            assert exc.code == "cost-declined"
        else:
            raise AssertionError("conversion should be declined")
        assert FakeChatHandler.calls == 0
    finally:
        server.shutdown()


def test_pdf_available_rejects_wrong_kind_and_accepts_arxiv_without_path(tmp_path: Path) -> None:
    settings = load_settings(None, {"llm.base_url": "http://localhost:11434/v1"})
    engine = PdfEngine()
    local = EngineContext(
        InputSpec("latex-local", path=tmp_path / "missing.pdf", original="x"),
        settings,
        CacheManager(tmp_path / "cache"),
        tmp_path,
        lambda _: True,
    )
    assert engine.available(local) == (False, "pdf-input-kind")
    arxiv = EngineContext(
        InputSpec("arxiv", arxiv_id="2401.12345", version=1, original="2401.12345v1"),
        settings,
        CacheManager(tmp_path / "cache2"),
        tmp_path,
        lambda _: True,
    )
    assert engine.available(arxiv) == (True, "available")
