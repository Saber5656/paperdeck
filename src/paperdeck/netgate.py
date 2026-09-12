"""The single HTTP boundary for paperdeck, including SSRF defenses and caps."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

import httpx

from . import __version__
from .errors import ConfigError, FetchError, SecurityError

Purpose = Literal["arxiv", "llm"]
# Public aliases keep transport exception and response handling behind this
# single HTTP boundary. Engines and LLM code must not import httpx directly.
HttpResponse = httpx.Response
TimeoutException = httpx.TimeoutException
TransportError = httpx.TransportError
_ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
_LOG = logging.getLogger(__name__)


class RateLimiter:
    """Thread-safe minimum-interval limiter."""

    def __init__(
        self,
        min_interval: float = 3.0,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = threading.Lock()
        self._last: float | None = None

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last is not None:
                delay = self.min_interval - (now - self._last)
                if delay > 0:
                    self._sleep(delay)
                    now = self._clock()
            self._last = now


_ARXIV_RATE_LIMITER = RateLimiter()


class _CappedStream(httpx.SyncByteStream):
    def __init__(self, stream: httpx.SyncByteStream, cap: int) -> None:
        self._stream = stream
        self._cap = cap
        self._seen = 0

    def __iter__(self):  # type: ignore[no-untyped-def]
        for chunk in self._stream:
            self._seen += len(chunk)
            if self._seen > self._cap:
                raise FetchError(
                    "Response exceeded the configured size cap",
                    "use a smaller artifact or raise the configured fetch limit",
                    "size-cap",
                )
            yield chunk

    def close(self) -> None:
        self._stream.close()


class _GateTransport(httpx.BaseTransport):
    def __init__(
        self,
        inner: httpx.BaseTransport,
        purpose: Purpose,
        offline: bool,
        allowed_hosts: set[str],
        cap: int,
        upgrade_http: bool = False,
        exact_authority: str | None = None,
    ) -> None:
        self.inner, self.purpose, self.offline = inner, purpose, offline
        self.allowed_hosts, self.cap, self.upgrade_http, self.exact_authority = (
            allowed_hosts,
            cap,
            upgrade_http,
            exact_authority,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.offline:
            raise FetchError(
                "Network access is disabled in offline mode",
                "remove --offline or use cached artifacts",
                "offline",
            )
        host = (request.url.host or "").lower()
        authority = host if request.url.port is None else f"{host}:{request.url.port}"
        if host not in self.allowed_hosts or (
            self.exact_authority is not None and authority != self.exact_authority
        ):
            raise SecurityError(
                "Request host is not allowed: " + host,
                "use an approved arXiv or configured local LLM host",
                "host-not-allowed",
            )
        if self.purpose == "arxiv" and request.url.scheme == "http":
            request = httpx.Request(
                request.method,
                request.url.copy_with(scheme="https"),
                headers=request.headers,
                content=request.stream,
                extensions=request.extensions,
            )
        if self.purpose == "arxiv":
            _ARXIV_RATE_LIMITER.wait()
        response = self.inner.handle_request(request)
        # MockTransport and a few custom transports may eagerly populate the
        # private content buffer. Clear it so the cap is enforced by iteration
        # in exactly the same way as a real streamed response.
        if hasattr(response, "_content"):
            del response._content
            response.is_stream_consumed = False
            response.is_closed = False
        response.stream = _CappedStream(cast(httpx.SyncByteStream, response.stream), self.cap)
        return response

    def close(self) -> None:
        self.inner.close()


class NetGate:
    def __init__(self, settings, *, transport: httpx.BaseTransport | None = None) -> None:  # type: ignore[no-untyped-def]
        self.settings = settings
        self.offline = bool(settings.offline)
        self._transport = transport
        self._clients: dict[str, httpx.Client] = {}
        llm_url = str(settings.llm.base_url)
        parsed = httpx.URL(llm_url)
        if parsed.scheme == "http" and (parsed.host or "").lower() not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ConfigError(
                "Plain HTTP LLM URLs are allowed only for localhost",
                "use HTTPS for a remote LLM endpoint",
                "llm-http-not-local",
            )
        self._llm_host = (parsed.host or "").lower()
        self._llm_hostport = (
            self._llm_host if parsed.port is None else f"{self._llm_host}:{parsed.port}"
        )

    def client(self, purpose: Purpose) -> httpx.Client:
        if purpose in self._clients:
            return self._clients[purpose]
        if purpose == "arxiv":
            inner = self._transport or httpx.HTTPTransport(
                verify=True, limits=httpx.Limits(max_connections=1)
            )
            transport = _GateTransport(
                inner,
                purpose,
                self.offline,
                set(_ARXIV_HOSTS),
                int(self.settings.fetch.max_download_mb * 1024 * 1024),
                True,
            )
            client = httpx.Client(
                transport=transport,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=1),
                headers={
                    "User-Agent": f"paperdeck/{__version__} (+https://github.com/Saber5656/paperdeck)"
                },
                verify=True,
                timeout=float(self.settings.fetch.timeout_s),
            )
        else:
            inner = self._transport or httpx.HTTPTransport(verify=True)
            transport = _GateTransport(
                inner,
                purpose,
                self.offline,
                {self._llm_host},
                20 * 1024 * 1024,
                False,
                self._llm_hostport,
            )
            client = httpx.Client(
                transport=transport,
                follow_redirects=False,
                verify=True,
                timeout=float(
                    getattr(self.settings.llm, "timeout_s", self.settings.fetch.timeout_s)
                ),
            )
        self._clients[purpose] = client
        return client

    def download(self, url: str, dest: Path, purpose: Purpose) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + ".tmp")
        try:
            if temporary.exists():
                temporary.unlink()
            with self.client(purpose).stream("GET", url) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
                        output.flush()
                    os.fsync(output.fileno())
            os.replace(temporary, dest)
            _LOG.info("downloaded %s (%d bytes)", url, dest.stat().st_size)
            return dest
        except httpx.HTTPStatusError as exc:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise FetchError(
                f"HTTP request failed with status {exc.response.status_code}",
                "retry the request or check the remote artifact",
                f"http-{exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise FetchError(
                "Network request failed", "check your network connection and retry", "network-error"
            ) from exc
        except Exception:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise
