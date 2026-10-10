"""Stage 0 tests with mocked SEC endpoints (no network)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from pipeline.errors import ConfigError, DisallowedHost, InvalidTicker, NoTenKFound, TickerNotFound
from pipeline.http import AllowlistClient, check_host
from pipeline.sec_fetch import run_stage0, select_two_latest

TICKERS = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}


def submissions(forms):
    n = len(forms)
    return {
        "cik": "1045810",
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "accessionNumber": [f"0001045810-{25 - i:02d}-00000{i + 1}" for i in range(n)],
                "filingDate": [f"{2025 - i}-02-2{i}" for i in range(n)],
                "reportDate": [f"{2025 - i}-01-26" for i in range(n)],
                "form": forms,
                "primaryDocument": [f"nvda-{2025 - i}.htm" for i in range(n)],
            },
            "files": [],
        },
    }


HTML = '<html><body><ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="c">{fy}</ix:nonNumeric><p>ITEM 1A. RISK FACTORS</p></body></html>'


@pytest.fixture()
def sec_mock():
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=TICKERS)
        )
        mock.get("https://data.sec.gov/submissions/CIK0001045810.json").mock(
            return_value=httpx.Response(
                200, json=submissions(["8-K", "10-K", "10-Q", "10-K/A", "10-K", "10-K"])
            )
        )
        mock.get(
            url__regex=r"https://www\.sec\.gov/Archives/edgar/data/1045810/\d+/nvda-(\d{4})\.htm"
        ).mock(
            side_effect=lambda request, **kw: httpx.Response(
                200, text=HTML.format(fy=request.url.path[-8:-4])
            )
        )
        yield mock


def test_stage0_picks_two_latest_originals_and_caches(settings, sec_mock):
    res = run_stage0("nvda", settings)
    assert res.company.ticker == "NVDA"
    assert res.company.cik == "0001045810"
    assert res.new.accession_number == "0001045810-24-000002"  # the 10-K at index 1
    assert (
        res.old.accession_number == "0001045810-21-000005"
    )  # next original (index 4), skipping the 10-K/A
    assert res.new.form == "10-K" and res.old.form == "10-K"
    assert "amendments excluded" in res.selection_note
    assert (
        res.new.fiscal_year == 2024 and res.new.fiscal_year_source == "dei:DocumentFiscalYearFocus"
    )
    assert (
        res.new.edgar_url
        == "https://www.sec.gov/Archives/edgar/data/1045810/000104581024000002/nvda-2024.htm"
    )
    assert res.new.edgar_index_url.endswith("/0001045810-24-000002-index.htm")
    first_calls = sec_mock.calls.call_count
    assert first_calls == 4  # tickers + submissions + 2 documents

    # second run: zero network calls
    res2 = run_stage0("NVDA", settings)
    assert sec_mock.calls.call_count == first_calls
    assert res2.model_dump() == res.model_dump()

    for call in sec_mock.calls:
        assert call.request.headers["User-Agent"] == "RiskDiff Test test@example.com"


def test_stage0_requires_user_agent(settings, sec_mock):
    bad = settings.__class__(**{**settings.__dict__, "sec_user_agent": None})
    with pytest.raises(ConfigError):
        run_stage0("NVDA", bad)
    assert sec_mock.calls.call_count == 0


def test_unknown_ticker(settings, sec_mock):
    with pytest.raises(TickerNotFound):
        run_stage0("ZZZZ", settings)


def test_invalid_ticker_rejected_before_network(settings, sec_mock):
    for bad in ["", "nvda; rm -rf /", "TOOLONG1", "../x", "N V"]:
        with pytest.raises(InvalidTicker):
            run_stage0(bad, settings)
    assert sec_mock.calls.call_count == 0


def test_amendments_used_only_when_needed():
    rows = submissions(["10-K/A", "10-K", "10-K/A"])["filings"]["recent"]
    filings = [
        dict(zip(rows.keys(), vals, strict=True)) for vals in zip(*rows.values(), strict=True)
    ]
    old, new, note, _ = select_two_latest(filings)
    assert "amendments were included" in note
    assert {old["form"], new["form"]} == {"10-K/A", "10-K"}
    with pytest.raises(NoTenKFound):
        select_two_latest([f for f in filings if f["form"] == "10-K"])


def test_host_allowlist():
    assert check_host("https://www.sec.gov/x") == "www.sec.gov"
    for url in [
        "http://www.sec.gov/x",
        "https://evil.example.com/",
        "https://sec.gov.evil.com/",
        "https://127.0.0.1/",
    ]:
        with pytest.raises(DisallowedHost):
            check_host(url)
    with AllowlistClient("ua") as c, pytest.raises(DisallowedHost):
        c.get("https://example.com/")


def test_rate_limit_spacing(settings):
    import time

    from pipeline import http as http_mod

    with respx.mock() as mock:
        mock.get(url__regex=r"https://www\.sec\.gov/.*").mock(
            return_value=httpx.Response(200, text="ok")
        )
        with AllowlistClient("ua") as c:
            t0 = time.monotonic()
            for i in range(4):
                c.get(f"https://www.sec.gov/{i}")
            elapsed = time.monotonic() - t0
    assert elapsed >= 3 * http_mod.MIN_INTERVAL_SECONDS * 0.9


def test_sec_cache_files_written(settings, sec_mock):
    run_stage0("NVDA", settings)
    root = settings.cache_dir / "sec"
    assert (root / "company_tickers.json").exists()
    assert (root / "submissions" / "CIK0001045810.json").exists()
    docs = list((root / "filings").glob("*/*.htm"))
    assert len(docs) == 2
    assert (
        json.loads((root / "submissions" / "CIK0001045810.json").read_text())["name"]
        == "NVIDIA CORP"
    )
