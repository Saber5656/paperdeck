import json
from pathlib import Path

from paperdeck.input.cache import CacheManager
from paperdeck.llm.cache import LlmCache, request_key
from paperdeck.llm.schemas import PdfEquationLatexV1


def test_llm_cache_key_and_private_value_file(tmp_path: Path) -> None:
    manager = CacheManager(tmp_path / "paperdeck")
    cache = LlmCache(manager)
    messages_a = [{"role": "user", "content": "paper"}]
    messages_b = [{"content": "paper", "role": "user"}]
    key_a = request_key("local/model", messages_a, "pdf_equation_latex", "v1")
    key_b = request_key("local/model", messages_b, "pdf_equation_latex", "v1")
    assert key_a == key_b
    cache.bind_model(key_a, "local/model", "pdf_equation_latex", "v1")
    cache.put(key_a, '{"latex":"x","confidence":0.5}', {"prompt_tokens": 4})
    assert cache.get(key_a, PdfEquationLatexV1, "v1") is not None
    path = next((tmp_path / "paperdeck" / "llm").rglob("*.json"))
    payload = json.loads(path.read_text())
    assert "messages" not in payload and "Authorization" not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
