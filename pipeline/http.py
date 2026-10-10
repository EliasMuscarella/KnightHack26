"""Allowlisted, rate-limited HTTP client.

Every outbound request in the pipeline goes through `AllowlistClient`, which refuses any host
outside the allowlist (SSRF guard), sends the SEC User-Agent on sec.gov requests, enforces a
minimum interval between requests (SEC fair access: stay well under 5 requests/second), and
retries transient failures with backoff.
"""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlsplit

import httpx

from pipeline.errors import DisallowedHost, SecUnavailable

log = logging.getLogger(__name__)

SEC_HOSTS = frozenset({"www.sec.gov", "data.sec.gov"})
HF_HOSTS = frozenset({"huggingface.co", "router.huggingface.co", "api-inference.huggingface.co"})
GEMINI_HOSTS = frozenset({"generativelanguage.googleapis.com"})
ALLOWED_HOSTS = SEC_HOSTS | HF_HOSTS | GEMINI_HOSTS

MIN_INTERVAL_SECONDS = 0.34  # ~3 requests/second, under the SEC's 10/s and our own 5/s cap
MAX_RETRIES = 3
TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


def check_host(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DisallowedHost(f"Only https URLs are allowed, got {parts.scheme!r}")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise DisallowedHost(f"Host {host!r} is not on the outbound allowlist")
    return host


class RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


_sec_limiter = RateLimiter(MIN_INTERVAL_SECONDS)


class AllowlistClient:
    """Thin wrapper over httpx.Client. Use as a context manager."""

    def __init__(self, sec_user_agent: str | None, *, transport: httpx.BaseTransport | None = None):
        self.sec_user_agent = sec_user_agent
        self._client = httpx.Client(timeout=TIMEOUT, follow_redirects=False, transport=transport)
        self.request_count = 0

    def __enter__(self) -> AllowlistClient:
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response:
        host = check_host(url)
        hdrs = {"Accept-Encoding": "gzip, deflate"}
        if host in SEC_HOSTS:
            if not self.sec_user_agent:
                from pipeline.errors import ConfigError

                raise ConfigError("SEC_USER_AGENT is not set; refusing to contact sec.gov")
            hdrs["User-Agent"] = self.sec_user_agent
            hdrs["Host"] = host
        if headers:
            hdrs.update(headers)
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            if host in SEC_HOSTS:
                _sec_limiter.wait()
            try:
                self.request_count += 1
                resp = self._client.get(url, headers=hdrs)
            except httpx.HTTPError as e:
                last_exc = e
                log.warning("GET %s failed (%s), attempt %d", url, type(e).__name__, attempt + 1)
            else:
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    log.warning("GET %s -> %d, retrying", url, resp.status_code)
                    last_exc = None
                elif resp.status_code >= 400:
                    return resp
                else:
                    return resp
            time.sleep(min(8.0, 1.0 * (2**attempt)))
        if host in SEC_HOSTS:
            raise SecUnavailable(f"SEC request failed after retries: {url}") from last_exc
        raise SecUnavailable(f"Request failed after retries: {url}") from last_exc
