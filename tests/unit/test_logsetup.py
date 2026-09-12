import logging

from paperdeck.logsetup import configure_logging, progress, redact


def test_redact_masks_all_secret_shapes(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_KEY", "zz-customsecret987654")
    configure_logging(2, api_key_env="CUSTOM_KEY")
    text = redact("zz-customsecret987654 sk-test1234567890 Authorization: Bearer xyz")
    assert "zz-customsecret987654" not in text
    assert "sk-test1234567890" not in text
    assert "Bearer xyz" not in text


def test_configure_is_idempotent_and_progress_gated(capsys) -> None:
    configure_logging(0)
    root = logging.getLogger()
    count = len(root.handlers)
    configure_logging(1)
    assert len(root.handlers) == count
    progress("hello")
    assert "hello" in capsys.readouterr().err
    configure_logging(0, quiet=True)
    progress("hidden")
    assert "hidden" not in capsys.readouterr().err
