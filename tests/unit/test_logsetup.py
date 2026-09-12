import io
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


def test_logging_survives_closed_capture_and_numeric_format(monkeypatch):
    first = io.StringIO()
    monkeypatch.setattr("sys.stderr", first)
    configure_logging(1)
    first.close()
    second = io.StringIO()
    monkeypatch.setattr("sys.stderr", second)
    configure_logging(1)
    logging.getLogger("paperdeck.test").info("calls=%d cost=%.2f", 2, 0.25)
    assert "calls=2 cost=0.25" in second.getvalue()


def test_exception_traceback_is_redacted(capsys, monkeypatch):
    secret = "zz-customsecret987654"  # noqa: S105 -- synthetic redaction fixture
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    configure_logging(2)
    try:
        raise ValueError(secret)
    except ValueError:
        logging.getLogger("paperdeck.test").exception("failed")
    assert secret not in capsys.readouterr().err
