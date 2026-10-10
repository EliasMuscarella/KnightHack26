"""Ticker tape: Finnhub poller + snapshot, driven with a fake fetch and a fake clock (no network)."""

from __future__ import annotations

import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

from api import ticker_tape as tt
from api.ticker_tape import (
    STALE_AFTER_SECONDS,
    TAPE_SYMBOLS,
    Forbidden,
    KeyRejected,
    QuoteError,
    RateLimited,
    TickerTapeService,
)
from pipeline.config import Settings

T0 = 1_760_000_000.0  # 2025-10-09T08:53:20Z
FAKE_KEY = "fk-TEST-SECRET-9b1f2c"


class Clock:
    def __init__(self, t: float = T0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def quote(c, d=1.0, dp=0.5, pc=100.0):
    return {"c": c, "d": d, "dp": dp, "h": c, "l": c, "o": c, "pc": pc, "t": 1}


class FakeFetch:
    """symbol -> response dict, or an exception instance to raise. Records every call."""

    def __init__(self, responses=None, default=None):
        self.responses = dict(responses or {})
        self.default = default
        self.calls: list[str] = []

    def __call__(self, symbol):
        self.calls.append(symbol)
        r = self.responses.get(symbol, self.default)
        if isinstance(r, BaseException):
            raise r
        return r


def make(tmp_path, fetch, clock=None, key=FAKE_KEY, **kw):
    return TickerTapeService(
        tmp_path / "cache" / "ticker_tape.json", key, fetch=fetch, clock=clock or Clock(), **kw
    )


def symbols_of(snap):
    return [q["symbol"] for q in snap["quotes"]]


# ---------- symbol list ----------


def test_symbol_list_is_50_unique_valid_tickers():
    syms = [s for s, _ in TAPE_SYMBOLS]
    assert len(syms) == 50 and len(set(syms)) == 50
    assert all(re.fullmatch(r"^[A-Z.\-]{1,6}$", s) for s in syms)
    assert all(name.strip() for _, name in TAPE_SYMBOLS)
    assert syms[:3] == ["NVDA", "MSFT", "AAPL"] and syms[-1] == "DIS"


def test_default_fetch_refuses_symbols_not_on_the_tape():
    with pytest.raises(ValueError):
        tt.finnhub_fetch("https://evil.example/", "k")
    svc = TickerTapeService(tt.Path("/nonexistent/x.json"), None, fetch=FakeFetch())
    with pytest.raises(ValueError):
        svc.refresh_once("ZZZZ")


# ---------- snapshot ----------


def test_snapshot_shape_order_and_rounding(tmp_path):
    fetch = FakeFetch(
        {
            "MSFT": quote(512.3456, d=-3.14159, dp=-0.61234, pc=515.49),
            "NVDA": quote(181.005, d=2.0, dp=1.116, pc=179.0),
            "AAPL": quote(250.0, d=0.001, dp=None, pc=0),  # dp missing, pc 0 -> null pct
            "GOOGL": quote(200.0, d=4.0, dp=None, pc=196.0),  # dp computed from d/pc
            "AMZN": quote(220.0, d=None, dp=None, pc=200.0),  # d from c - pc
            "META": quote(700.0, d=-0.001, dp=-0.0001),  # tiny negatives round to 0.0, not -0.0
        }
    )
    svc = make(tmp_path, fetch)
    for s in ["MSFT", "NVDA", "AAPL", "GOOGL", "AMZN", "META"]:
        assert svc.refresh_once(s) == "ok"
    snap = svc.snapshot()
    assert set(snap) == {"status", "source", "as_of", "quotes"}
    assert snap["status"] == "ok" and snap["source"] == "Finnhub"
    assert snap["as_of"] == "2025-10-09T08:53:20Z"
    assert symbols_of(snap) == ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META"]  # tape order
    by = {q["symbol"]: q for q in snap["quotes"]}
    assert by["MSFT"] == {
        "symbol": "MSFT",
        "name": "Microsoft",
        "price": 512.35,
        "change": -3.14,
        "change_pct": -0.61,
        "updated_at": "2025-10-09T08:53:20Z",
    }
    assert by["NVDA"]["price"] == 181.0 and by["NVDA"]["change_pct"] == 1.12
    assert by["AAPL"]["change_pct"] is None and by["AAPL"]["change"] == 0.0
    assert by["GOOGL"]["change_pct"] == 2.04
    assert by["AMZN"]["change"] == 20.0 and by["AMZN"]["change_pct"] == 10.0
    assert json.dumps(by["META"]).count("-0.0") == 0
    assert all(isinstance(q["price"], float) for q in snap["quotes"])


def test_empty_snapshot_is_unavailable(tmp_path):
    svc = make(tmp_path, FakeFetch())
    assert svc.snapshot() == {
        "status": "unavailable",
        "source": "Finnhub",
        "as_of": None,
        "quotes": [],
    }


def test_zero_or_non_numeric_price_is_skipped(tmp_path):
    fetch = FakeFetch(
        {
            "NVDA": {"c": 0, "d": None, "dp": None, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0},
            "MSFT": quote("12.5"),
            "AAPL": quote(float("nan")),
            "GOOGL": quote(True),
            "AMZN": {"error": "nope"},
        }
    )
    svc = make(tmp_path, fetch)
    for s in ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN"]:
        assert svc.refresh_once(s) == "no_data"
    assert svc.snapshot()["status"] == "unavailable"


def test_no_data_keeps_previous_quote(tmp_path):
    fetch = FakeFetch({"NVDA": quote(100.0)})
    svc = make(tmp_path, fetch)
    svc.refresh_once("NVDA")
    fetch.responses["NVDA"] = quote(0)
    assert svc.refresh_once("NVDA") == "no_data"
    assert svc.snapshot()["quotes"][0]["price"] == 100.0


# ---------- errors ----------


def test_network_error_keeps_last_good_quote(tmp_path):
    clock = Clock()
    fetch = FakeFetch({"NVDA": quote(100.0)})
    svc = make(tmp_path, fetch, clock)
    assert svc.refresh_once("NVDA") == "ok"
    clock.t += 60
    for err in (QuoteError("ConnectTimeout"), QuoteError("HTTP 502"), TimeoutError(), None):
        fetch.responses["NVDA"] = err
        assert svc.refresh_once("NVDA") == "error"
    snap = svc.snapshot()
    assert snap["status"] == "ok" and snap["quotes"][0]["price"] == 100.0
    assert snap["quotes"][0]["updated_at"] == "2025-10-09T08:53:20Z"  # time of the good quote


def test_rate_limit_backs_off_60s_and_retries_same_symbol(tmp_path):
    fetch = FakeFetch({"NVDA": RateLimited("HTTP 429")}, default=quote(10.0))
    svc = make(tmp_path, fetch)
    assert svc.step() == 60.0
    assert svc.step() == 60.0
    fetch.responses.pop("NVDA")
    assert svc.step() == pytest.approx(1.2)
    assert svc.step() == pytest.approx(1.2)
    assert fetch.calls == ["NVDA", "NVDA", "NVDA", "MSFT"]
    assert symbols_of(svc.snapshot()) == ["NVDA", "MSFT"]


def test_round_robin_paces_under_free_tier_limit(tmp_path):
    fetch = FakeFetch(default=quote(10.0))
    svc = make(tmp_path, fetch)
    delays = [svc.step() for _ in range(len(TAPE_SYMBOLS) + 1)]
    assert fetch.calls == [s for s, _ in TAPE_SYMBOLS] + ["NVDA"]
    assert all(d == pytest.approx(1.2) for d in delays)
    assert 60 / delays[0] <= 55  # requests per minute, under Finnhub's 60
    assert len(svc.snapshot()["quotes"]) == 50


def test_consecutive_failures_back_off_exponentially_with_cap(tmp_path):
    fetch = FakeFetch(default=QuoteError("ConnectError"))
    svc = make(tmp_path, fetch)
    delays = [svc.step() for _ in range(20)]
    assert delays[:4] == [pytest.approx(1.2)] * 4
    assert delays[4] > 1.2 and all(b >= a for a, b in zip(delays[4:], delays[5:], strict=False))
    assert max(delays) == 300.0 and delays[-1] == 300.0
    fetch.default = quote(5.0)
    assert svc.step() == pytest.approx(1.2)  # one success resets the backoff


def test_401_rejects_key_and_stops(tmp_path):
    clock = Clock()
    fetch = FakeFetch({"NVDA": quote(100.0), "MSFT": KeyRejected("HTTP 401")})
    svc = make(tmp_path, fetch, clock)
    assert svc.step() == pytest.approx(1.2)
    assert svc.step() is None
    assert svc.key_rejected
    assert svc.step() is None and fetch.calls == ["NVDA", "MSFT"]  # no more requests
    snap = svc.snapshot()
    assert snap["status"] == "stale" and symbols_of(snap) == ["NVDA"]  # data kept, marked stale
    assert svc.start() is False


def test_401_without_data_is_unavailable(tmp_path):
    svc = make(tmp_path, FakeFetch(default=KeyRejected("HTTP 401")))
    assert svc.step() is None
    assert svc.snapshot()["status"] == "unavailable"


def test_single_403_skips_symbol_repeated_403_rejects_key(tmp_path):
    fetch = FakeFetch({"MSFT": Forbidden("HTTP 403")}, default=quote(10.0))
    svc = make(tmp_path, fetch)
    for _ in range(3):  # NVDA ok, MSFT 403 (skipped), AAPL ok
        assert svc.step() == pytest.approx(1.2)
    assert not svc.key_rejected
    fetch.default = Forbidden("HTTP 403")
    assert svc.step() == pytest.approx(1.2)
    assert svc.step() == pytest.approx(1.2)
    assert svc.step() is None and svc.key_rejected
    assert svc.snapshot()["status"] == "stale"


def test_stale_after_five_minutes(tmp_path):
    clock = Clock()
    svc = make(tmp_path, FakeFetch(default=quote(10.0)), clock)
    svc.refresh_once("NVDA")
    clock.t += STALE_AFTER_SECONDS
    assert svc.snapshot()["status"] == "ok"
    clock.t += 1
    assert svc.snapshot()["status"] == "stale"
    svc.refresh_once("MSFT")  # any fresh quote advances as_of
    snap = svc.snapshot()
    assert snap["status"] == "ok" and snap["as_of"] == "2025-10-09T08:58:21Z"


# ---------- disk cache ----------


def test_cache_persists_and_reloads_after_restart(tmp_path):
    clock = Clock()
    fetch = FakeFetch(default=quote(42.424, d=1.234, dp=3.0))
    svc = make(tmp_path, fetch, clock)
    svc.refresh_once("NVDA")  # first write is immediate
    path = tmp_path / "cache" / "ticker_tape.json"
    assert path.exists()
    clock.t += 10
    svc.refresh_once("MSFT")  # within 30 s of the last write: not persisted yet
    assert set(json.loads(path.read_text())["quotes"]) == {"NVDA"}
    clock.t += 30
    svc.refresh_once("AAPL")
    assert set(json.loads(path.read_text())["quotes"]) == {"NVDA", "MSFT", "AAPL"}
    assert FAKE_KEY not in path.read_text()
    assert not list(path.parent.glob("*.tmp"))
    before = svc.snapshot()

    # restart shortly after: prices are shown at once, still fresh
    again = make(tmp_path, FakeFetch(), Clock(clock.t + 5))
    assert again.snapshot() == before and before["status"] == "ok"
    # restart much later: same prices, marked stale until refreshed
    later_clock = Clock(clock.t + 3600)
    later = make(tmp_path, FakeFetch(default=quote(50.0)), later_clock)
    snap = later.snapshot()
    assert snap["status"] == "stale" and snap["quotes"] == before["quotes"]
    later.refresh_once("NVDA")
    snap = later.snapshot()
    assert snap["status"] == "ok" and snap["quotes"][0]["price"] == 50.0
    # restart without a key: the last prices are shown but never claimed live
    nokey = TickerTapeService(path, None, clock=Clock(clock.t + 5))
    assert nokey.snapshot()["status"] == "stale" and len(nokey.snapshot()["quotes"]) == 3


def test_stop_flushes_pending_quotes(tmp_path):
    clock = Clock()
    svc = make(tmp_path, FakeFetch(default=quote(1.0)), clock)
    svc.refresh_once("NVDA")
    svc.refresh_once("MSFT")
    svc.stop()
    path = tmp_path / "cache" / "ticker_tape.json"
    assert set(json.loads(path.read_text())["quotes"]) == {"NVDA", "MSFT"}


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        json.dumps({"version": 99, "quotes": {}}),
        json.dumps({"version": 1, "quotes": []}),
        "",
    ],
)
def test_corrupt_cache_is_ignored(tmp_path, content):
    path = tmp_path / "cache" / "ticker_tape.json"
    path.parent.mkdir(parents=True)
    path.write_text(content)
    svc = make(tmp_path, FakeFetch(default=quote(3.0)))
    assert svc.snapshot()["status"] == "unavailable"
    assert svc.refresh_once("NVDA") == "ok"


def test_invalid_cache_entries_are_dropped(tmp_path):
    path = tmp_path / "cache" / "ticker_tape.json"
    path.parent.mkdir(parents=True)
    good = {"price": 10.0, "change": 1.0, "change_pct": None, "updated_at": T0}
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "quotes": {
                    "NVDA": good,
                    "EVIL": good,  # not on the tape
                    "MSFT": {**good, "price": "10"},
                    "AAPL": {**good, "price": -1},
                    "GOOGL": {**good, "updated_at": None},
                    "AMZN": {**good, "change_pct": "x"},
                },
            }
        )
    )
    assert symbols_of(make(tmp_path, FakeFetch()).snapshot()) == ["NVDA"]


# ---------- thread lifecycle ----------


def _tape_threads():
    return [t for t in threading.enumerate() if t.name == "ticker-tape"]


def test_no_key_starts_no_thread_and_makes_no_calls(tmp_path):
    fetch = FakeFetch(default=quote(1.0))
    for key in (None, "", "   "):
        svc = make(tmp_path, fetch, key=key)
        assert svc.start() is False and not svc.configured
    assert not _tape_threads() and fetch.calls == []


def test_background_loop_uses_injected_sleep_and_is_idempotent(tmp_path):
    fetch = FakeFetch(default=quote(7.0))
    sleeps: list[float] = []
    done = threading.Event()
    svc = None

    def sleep(d):
        sleeps.append(d)
        if len(sleeps) >= 5:
            svc._stop.set()
            done.set()

    svc = make(tmp_path, fetch, sleep=sleep)
    assert svc.start() is True
    assert svc.start() is True  # idempotent: still a single thread
    assert done.wait(5)
    svc.stop()
    assert not _tape_threads()
    assert fetch.calls[:5] == [s for s, _ in TAPE_SYMBOLS][:5]
    assert sleeps[:5] == [pytest.approx(1.2)] * 5


def test_loop_survives_unexpected_exceptions(tmp_path):
    calls = []

    def boom(symbol):
        calls.append(symbol)
        raise RuntimeError("unexpected")

    svc = make(tmp_path, boom)
    assert svc.step() == pytest.approx(1.2)  # counted as a transient failure, loop continues
    assert svc.snapshot()["status"] == "unavailable"


# ---------- API ----------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import api.main as api_main

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("RISKDIFF_EMBED_BACKEND", "lexical")
    settings = Settings(
        sec_user_agent=None,
        hf_token=None,
        gemini_api_key=None,
        data_dir=tmp_path / "data",
        embed_model="x",
        llm_model="x",
        gemini_model="y",
        api_origin="http://localhost:3000",
    )
    app = api_main.create_app(settings)
    with TestClient(app) as c:
        yield c


def test_endpoint_without_key_is_unavailable_and_starts_nothing(client):
    state = client.app.state.rd
    assert state.ticker_tape.configured is False
    assert not _tape_threads()
    r = client.get("/ticker-tape")
    assert r.status_code == 200
    assert r.json() == {"status": "unavailable", "source": "Finnhub", "as_of": None, "quotes": []}


def test_endpoint_serves_snapshot_and_never_leaks_key(client, tmp_path):
    state = client.app.state.rd
    fetch = FakeFetch(default=quote(123.456, d=-1.0, dp=-0.8))
    svc = TickerTapeService(tmp_path / "tape.json", FAKE_KEY, fetch=fetch, clock=Clock())
    for s, _ in TAPE_SYMBOLS[:3]:
        svc.refresh_once(s)
    state.ticker_tape = svc  # never started: no thread, no network
    r = client.get("/ticker-tape", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["as_of"] == "2025-10-09T08:53:20Z"
    assert [q["symbol"] for q in body["quotes"]] == ["NVDA", "MSFT", "AAPL"]
    assert body["quotes"][0]["price"] == 123.46
    assert FAKE_KEY not in r.text and FAKE_KEY not in json.dumps(dict(r.headers))
    assert FAKE_KEY not in (tmp_path / "tape.json").read_text()


def test_endpoint_never_5xx(client):
    class Broken:
        def snapshot(self):
            raise RuntimeError("boom " + FAKE_KEY)

        def stop(self):
            pass

    client.app.state.rd.ticker_tape = Broken()
    r = client.get("/ticker-tape")
    assert r.status_code == 200
    assert r.json()["status"] == "unavailable" and FAKE_KEY not in r.text
