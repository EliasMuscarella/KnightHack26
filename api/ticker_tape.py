"""Home-page ticker tape: day quotes for a fixed list of large US-listed stocks, from Finnhub.

Reliability model (web requests never call Finnhub):

* One daemon thread walks TAPE_SYMBOLS round-robin, one request every REQUEST_INTERVAL_SECONDS
  (~50 calls/min, under the free tier's 60/min), so every quote refreshes about once a minute.
* Requests read an in-memory, lock-protected snapshot. A failed fetch never removes data: the
  last good quote for a symbol is kept until a newer good one arrives.
* HTTP 429 -> wait RATE_LIMIT_BACKOFF_SECONDS. HTTP 401 (or repeated 403s across symbols) -> the
  key is rejected: the loop stops and the snapshot is reported "stale" (or "unavailable" when there
  is nothing cached). Network errors, timeouts, 5xx and malformed bodies keep the last quote and,
  after several in a row, back off exponentially up to MAX_BACKOFF_SECONDS.
* The snapshot is persisted atomically (temp file + os.replace) at most every PERSIST_EVERY_SECONDS
  and loaded on construction, so a restarted API shows the last known prices immediately.

Security: the URL is a constant, the only query parameter is a symbol from TAPE_SYMBOLS (never user
input), and the API key travels in the X-Finnhub-Token header. The key is never logged, persisted,
or returned. Quotes are market data for display only; they are not part of any RiskDiff analysis.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("api.ticker_tape")

SOURCE = "Finnhub"
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
HTTP_TIMEOUT_SECONDS = 5.0
REQUEST_INTERVAL_SECONDS = 1.2
RATE_LIMIT_BACKOFF_SECONDS = 60.0
FAILURES_BEFORE_BACKOFF = 5
MAX_BACKOFF_SECONDS = 300.0
FORBIDDEN_BEFORE_REJECT = 3  # consecutive 403s (no success between) before the key is deemed bad
STALE_AFTER_SECONDS = 300
PERSIST_EVERY_SECONDS = 30.0
CACHE_FORMAT_VERSION = 1

# A snapshot ranking of the 50 largest US-listed companies by market capitalization, taken when
# this list was written. It does not update itself: refresh it by hand. Order here is display order.
TAPE_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("NVDA", "NVIDIA"),
    ("MSFT", "Microsoft"),
    ("AAPL", "Apple"),
    ("GOOGL", "Alphabet"),
    ("AMZN", "Amazon"),
    ("META", "Meta"),
    ("AVGO", "Broadcom"),
    ("TSLA", "Tesla"),
    ("BRK.B", "Berkshire Hathaway"),
    ("TSM", "TSMC"),
    ("JPM", "JPMorgan Chase"),
    ("WMT", "Walmart"),
    ("LLY", "Eli Lilly"),
    ("ORCL", "Oracle"),
    ("V", "Visa"),
    ("MA", "Mastercard"),
    ("NFLX", "Netflix"),
    ("XOM", "Exxon Mobil"),
    ("COST", "Costco"),
    ("JNJ", "Johnson & Johnson"),
    ("PLTR", "Palantir"),
    ("HD", "Home Depot"),
    ("ABBV", "AbbVie"),
    ("BAC", "Bank of America"),
    ("PG", "Procter & Gamble"),
    ("AMD", "AMD"),
    ("UNH", "UnitedHealth"),
    ("KO", "Coca-Cola"),
    ("GE", "GE Aerospace"),
    ("CVX", "Chevron"),
    ("CSCO", "Cisco"),
    ("ASML", "ASML"),
    ("WFC", "Wells Fargo"),
    ("IBM", "IBM"),
    ("MU", "Micron"),
    ("MS", "Morgan Stanley"),
    ("PM", "Philip Morris"),
    ("GS", "Goldman Sachs"),
    ("CAT", "Caterpillar"),
    ("AXP", "American Express"),
    ("MRK", "Merck"),
    ("CRM", "Salesforce"),
    ("LIN", "Linde"),
    ("ABT", "Abbott"),
    ("MCD", "McDonald's"),
    ("RTX", "RTX"),
    ("T", "AT&T"),
    ("PEP", "PepsiCo"),
    ("TMUS", "T-Mobile US"),
    ("DIS", "Disney"),
)
_NAMES: dict[str, str] = dict(TAPE_SYMBOLS)

# Fetch outcomes (returned by TickerTapeService.refresh_once)
OK, NO_DATA, ERROR, RATE_LIMITED, KEY_REJECTED, FORBIDDEN = (
    "ok",
    "no_data",
    "error",
    "rate_limited",
    "key_rejected",
    "forbidden",
)


class QuoteError(Exception):
    """Transient failure (network, timeout, 5xx, malformed body): keep the last quote, retry."""


class RateLimited(QuoteError):
    """HTTP 429."""


class KeyRejected(QuoteError):
    """HTTP 401: the API key is invalid."""


class Forbidden(QuoteError):
    """HTTP 403: no access (bad key, or a symbol outside the plan)."""


Fetch = Callable[[str], dict | None]

# ---------- default fetch (the only code that talks to Finnhub) ----------

_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _http_client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=False)
        return _client


def finnhub_fetch(symbol: str, api_key: str) -> dict:
    """GET one quote. Raises a QuoteError subclass on any failure; returns the JSON object."""
    if symbol not in _NAMES:  # never a user-supplied value: only the fixed list is ever requested
        raise ValueError("symbol is not on the ticker tape")
    try:
        r = _http_client().get(
            FINNHUB_QUOTE_URL,
            params={"symbol": symbol},
            headers={"X-Finnhub-Token": api_key, "Accept": "application/json"},
        )
    except httpx.HTTPError as e:
        raise QuoteError(type(e).__name__) from None  # no message: it could echo request details
    if r.status_code == 429:
        raise RateLimited("HTTP 429")
    if r.status_code == 401:
        raise KeyRejected("HTTP 401")
    if r.status_code == 403:
        raise Forbidden("HTTP 403")
    if r.status_code != 200:
        raise QuoteError(f"HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise QuoteError("malformed JSON") from None
    if not isinstance(data, dict):
        raise QuoteError("unexpected JSON")
    return data


# ---------- helpers ----------


def _num(v: Any) -> float | None:
    """A finite float, or None (bools, strings, NaN and infinities are not numbers here)."""
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _r2(v: float) -> float:
    return round(v, 2) + 0.0  # + 0.0 turns -0.0 into 0.0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_quote(data: Any) -> dict[str, float | None] | None:
    """Finnhub quote JSON -> {price, change, change_pct} rounded to cents, or None (no data)."""
    if not isinstance(data, dict):
        return None
    c = _num(data.get("c"))
    if c is None or c <= 0:  # unknown symbols come back as c=0
        return None
    d, dp, pc = _num(data.get("d")), _num(data.get("dp")), _num(data.get("pc"))
    if d is None:
        if pc is None or pc <= 0:
            return None  # a change cannot be stated honestly
        d = c - pc
    if dp is None and pc is not None and pc != 0:
        dp = d / pc * 100.0
    return {"price": _r2(c), "change": _r2(d), "change_pct": None if dp is None else _r2(dp)}


def _valid_cached(entry: Any) -> dict[str, float | None] | None:
    if not isinstance(entry, dict):
        return None
    price, change, ts = _num(entry.get("price")), _num(entry.get("change")), entry.get("updated_at")
    pct = entry.get("change_pct")
    if price is None or price <= 0 or change is None or _num(ts) is None or _num(ts) <= 0:
        return None
    if pct is not None and _num(pct) is None:
        return None
    return {
        "price": _r2(price),
        "change": _r2(change),
        "change_pct": None if pct is None else _r2(float(pct)),
        "updated_at": float(ts),
    }


def unavailable_body() -> dict[str, Any]:
    return {"status": "unavailable", "source": SOURCE, "as_of": None, "quotes": []}


# ---------- service ----------


class TickerTapeService:
    """Background Finnhub poller + in-memory snapshot. Thread-safe; `snapshot()` never does I/O."""

    def __init__(
        self,
        cache_path: Path,
        api_key: str | None,
        *,
        fetch: Fetch | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Any] | None = None,
    ):
        self._cache_path = Path(cache_path)
        self._api_key = (api_key or "").strip() or None
        key = self._api_key
        self._fetch: Fetch = fetch or (lambda symbol: finnhub_fetch(symbol, key or ""))
        self._clock = clock
        self._stop = threading.Event()
        self._sleep = sleep or self._stop.wait
        self._lock = threading.Lock()
        self._persist_lock = threading.Lock()
        self._quotes: dict[str, dict[str, float | None]] = {}
        self._key_rejected = False
        self._index = 0
        self._failures = 0  # consecutive transient failures
        self._forbidden = 0  # consecutive 403s
        self._dirty = False
        self._last_persist = -math.inf
        self._thread: threading.Thread | None = None
        self._load_cache()

    # ----- lifecycle -----

    @property
    def configured(self) -> bool:
        return self._api_key is not None

    @property
    def key_rejected(self) -> bool:
        return self._key_rejected

    def start(self) -> bool:
        """Start the poller once. No-op (False) without an API key or after the key was rejected."""
        if not self.configured or self._key_rejected:
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="ticker-tape", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the poller (if running) and flush the snapshot to disk."""
        self._stop.set()
        th = self._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout)
        self.persist(force=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                delay = self.step()
            except Exception as e:  # noqa: BLE001  (the poller must never die)
                log.warning("ticker tape step failed: %s", type(e).__name__)
                delay = REQUEST_INTERVAL_SECONDS
            if delay is None:
                break
            self._sleep(delay)

    # ----- polling -----

    def step(self) -> float | None:
        """Fetch the next symbol; return seconds to wait before the next step, None to stop."""
        if self._key_rejected:
            return None
        symbol = TAPE_SYMBOLS[self._index][0]
        outcome = self.refresh_once(symbol)
        if outcome == RATE_LIMITED:
            return RATE_LIMIT_BACKOFF_SECONDS  # retry the same symbol after the window resets
        self._index = (self._index + 1) % len(TAPE_SYMBOLS)
        if outcome == KEY_REJECTED:
            return None
        if outcome == ERROR and self._failures >= FAILURES_BEFORE_BACKOFF:
            exp = self._failures - FAILURES_BEFORE_BACKOFF
            return min(MAX_BACKOFF_SECONDS, REQUEST_INTERVAL_SECONDS * 2 ** (exp + 1))
        return REQUEST_INTERVAL_SECONDS

    def refresh_once(self, symbol: str) -> str:
        """Fetch and apply one quote. Returns the outcome; never raises for fetch failures."""
        if symbol not in _NAMES:
            raise ValueError("symbol is not on the ticker tape")
        try:
            data = self._fetch(symbol)
        except RateLimited:
            log.info("ticker tape: Finnhub rate limit hit; backing off")
            return RATE_LIMITED
        except KeyRejected:
            self._reject_key("HTTP 401")
            return KEY_REJECTED
        except Forbidden:
            self._forbidden += 1
            if self._forbidden >= FORBIDDEN_BEFORE_REJECT:
                self._reject_key("HTTP 403")
                return KEY_REJECTED
            return FORBIDDEN
        except Exception as e:  # noqa: BLE001  (network, timeout, 5xx, malformed: keep last quote)
            self._failures += 1
            if self._failures in (1, FAILURES_BEFORE_BACKOFF) or self._failures % 50 == 0:
                log.warning(
                    "ticker tape: quote fetch failed (%s), %d in a row",
                    type(e).__name__,
                    self._failures,
                )
            return ERROR
        if data is None:  # the fetch reported no usable body
            self._failures += 1
            return ERROR
        self._failures = 0
        self._forbidden = 0
        quote = parse_quote(data)
        if quote is None:
            return NO_DATA
        now = self._clock()
        with self._lock:
            self._quotes[symbol] = {**quote, "updated_at": now}
            self._dirty = True
        self.persist()
        return OK

    def _reject_key(self, why: str) -> None:
        if not self._key_rejected:
            self._key_rejected = True
            log.warning(
                "ticker tape: Finnhub rejected the API key (%s); quote refresh stopped", why
            )
        self.persist(force=True)

    # ----- snapshot -----

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = [(s, n, dict(self._quotes[s])) for s, n in TAPE_SYMBOLS if s in self._quotes]
        if not items:
            return unavailable_body()
        as_of = max(q["updated_at"] for _, _, q in items)
        stale = (
            self._key_rejected or not self.configured or self._clock() - as_of > STALE_AFTER_SECONDS
        )
        return {
            "status": "stale" if stale else "ok",
            "source": SOURCE,
            "as_of": _iso(as_of),
            "quotes": [
                {
                    "symbol": s,
                    "name": n,
                    "price": q["price"],
                    "change": q["change"],
                    "change_pct": q["change_pct"],
                    "updated_at": _iso(q["updated_at"]),
                }
                for s, n, q in items
            ],
        }

    # ----- disk cache -----

    def persist(self, *, force: bool = False) -> bool:
        """Write the snapshot atomically when dirty and PERSIST_EVERY_SECONDS have passed."""
        with self._persist_lock:
            now = self._clock()
            with self._lock:
                if not self._dirty or (
                    not force and now - self._last_persist < PERSIST_EVERY_SECONDS
                ):
                    return False
                doc = {
                    "version": CACHE_FORMAT_VERSION,
                    "source": SOURCE,
                    "quotes": {s: dict(q) for s, q in self._quotes.items()},
                }
                self._dirty = False
                self._last_persist = now
            tmp = self._cache_path.with_name(f".{self._cache_path.name}.{os.getpid()}.tmp")
            try:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")))
                os.replace(tmp, self._cache_path)
                return True
            except OSError as e:
                log.warning("ticker tape: could not save the quote cache (%s)", type(e).__name__)
                with self._lock:
                    self._dirty = True
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                return False

    def _load_cache(self) -> None:
        try:
            doc = json.loads(self._cache_path.read_text())
        except (OSError, ValueError):
            return  # missing or corrupt: start empty
        if not isinstance(doc, dict) or doc.get("version") != CACHE_FORMAT_VERSION:
            return
        quotes = doc.get("quotes")
        if not isinstance(quotes, dict):
            return
        loaded = {}
        for symbol, entry in quotes.items():
            if symbol in _NAMES and (q := _valid_cached(entry)) is not None:
                loaded[symbol] = q
        with self._lock:
            self._quotes = loaded
