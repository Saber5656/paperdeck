from paperdeck.engines.latex.engine import _created_at


def test_fake_now_is_only_honored_inside_pytest(monkeypatch) -> None:
    monkeypatch.setenv("PAPERDECK_FAKE_NOW", "2000-01-01T00:00:00+00:00")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "clock-test")
    assert _created_at() == "2000-01-01T00:00:00+00:00"
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert _created_at() != "2000-01-01T00:00:00+00:00"
