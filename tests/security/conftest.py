from collections.abc import Iterator

import pytest

from .fake_llm import FakeLLM


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    with FakeLLM() as server:
        yield server
