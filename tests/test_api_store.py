"""D4/D6: the API against a fake shared store: library merge, read-through cache (local hit,
remote hit, remote offline), integrity rejection, health and trends."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from pipeline.config import Settings
from pipeline.schema import Comparison, canonical_json
from pipeline.store import (
    StoreDisabled,
    StoreIntegrityError,
    StoreUnavailable,
    recompute_analysis_id,
)
from tests.test_store import real_doc

ROOT = Path(__file__).resolve().parents[1]


def make_doc(ticker: str, fingerprint: str | None = None) -> tuple[Comparison, bytes]:
    d = real_doc()
    d["company"]["ticker"] = ticker
    if fingerprint:
        d["code_fingerprint"] = fingerprint
    comp = Comparison.model_validate(d)
    d["analysis_id"] = recompute_analysis_id(comp)
    comp = Comparison.model_validate(d)
    return comp, canonical_json(comp).encode("utf-8")


def row_for(
    comp: Comparison, data: bytes, *, by: str = "alice", at: str = "2026-10-10T20:00:00Z"
) -> dict:
    by_ct = comp.summary.by_change_type
    return {
        "analysis_id": comp.analysis_id,
        "ticker": comp.company.ticker,
        "company_name": comp.company.name,
        "cik": comp.company.cik,
        "old_fiscal_year": comp.old_filing.fiscal_year,
        "new_fiscal_year": comp.new_filing.fiscal_year,
        "old_accession": comp.old_filing.accession_number,
        "new_accession": comp.new_filing.accession_number,
        "old_filing_date": comp.old_filing.filing_date,
        "new_filing_date": comp.new_filing.filing_date,
        "pipeline_version": comp.pipeline_version,
        "rubric_version": comp.rubric_version,
        "published_at": at,
        "published_by": by,
        "volume_path": f"/Volumes/riskdiff/main/reports/{comp.company.ticker}/{comp.analysis_id}.json",
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "is_current": True,
        "total_changes": comp.summary.total_changes,
        "max_score": comp.summary.max_score,
        **{f"n_{k}": v for k, v in by_ct.items()},
    }


class FakeStore:
    """Duck-typed stand-in for DatabricksStore as the API uses it."""

    def __init__(self, rows: list[dict], files: dict[str, bytes], *, offline: bool = False):
        self.rows = rows
        self.files = files
        self.offline = offline
        self.downloads = 0
        self.list_calls = 0
        self.settings = type("S", (), {"table": lambda self, n: f"`riskdiff`.`main`.`{n}`"})()
        self.trend_rows: dict[str, list[dict]] = {}

    def _check(self):
        if self.offline:
            raise StoreUnavailable("Databricks unreachable after 3 attempts (ConnectionError)")

    def list_reports(self):
        self._check()
        self.list_calls += 1
        return list(self.rows)

    def download_report(self, analysis_id, *, volume_path=None, content_sha256=None):
        self._check()
        self.downloads += 1
        data = self.files[volume_path]
        if content_sha256 and hashlib.sha256(data).hexdigest() != content_sha256:
            raise StoreIntegrityError("report bytes do not match the hash recorded at publish time")
        from pipeline.store import verify_report

        return verify_report(data, analysis_id), data

    def health(self):
        self._check()
        return {"remote": "ok"}

    def execute(self, sql, params=None):
        self._check()
        if "COUNT(DISTINCT ticker)" in sql:
            return [{"companies": len({r["ticker"] for r in self.rows})}]
        if "LATERAL VIEW explode" in sql:
            return self.trend_rows.get("by_category", [])
        return self.trend_rows.get("by_kind", [])


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        sec_user_agent=None,
        hf_token=None,
        gemini_api_key=None,
        data_dir=tmp_path / "data",
        embed_model="x",
        llm_model="x",
        gemini_model="y",
        api_origin="http://localhost:3000",
    )


@pytest.fixture
def world(tmp_path):
    """Local: TEST on disk. Remote: TEST (same analysis, with publisher) + ACME (remote only)."""
    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    test_comp, test_bytes = make_doc("TEST")
    (settings.published_dir / "TEST_2024_2025.json").write_bytes(test_bytes)
    acme_comp, acme_bytes = make_doc("ACME")
    rows = [row_for(test_comp, test_bytes, by="alice"), row_for(acme_comp, acme_bytes, by="bob")]
    files = {rows[0]["volume_path"]: test_bytes, rows[1]["volume_path"]: acme_bytes}
    store = FakeStore(rows, files)
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as c:
        yield c, store, settings, {"TEST": (test_comp, test_bytes), "ACME": (acme_comp, acme_bytes)}


def wait_for_list(store: FakeStore, timeout: float = 5.0) -> None:
    t0 = time.monotonic()
    while store.list_calls == 0 and time.monotonic() - t0 < timeout:
        time.sleep(0.02)


def test_companies_merges_remote_and_local_deduplicated(world):
    client, store, _, docs = world
    wait_for_list(store)
    r = client.get("/companies")
    assert r.status_code == 200
    cards = {c["ticker"]: c for c in r.json()["companies"]}
    assert set(cards) == {"ACME", "TEST"}
    assert cards["TEST"]["source"] == "local"  # same analysis on both sides -> one local card
    assert cards["TEST"]["published_by"] == "alice" and cards["TEST"]["published_at"].startswith(
        "2026-10-10"
    )
    assert cards["TEST"]["analysis_id"] == docs["TEST"][0].analysis_id
    assert cards["ACME"]["source"] == "remote" and cards["ACME"]["published_by"] == "bob"
    assert "content_sha256" not in cards["ACME"] and "volume_path" not in cards["ACME"]
    # list is cached: a second call does not hit the warehouse again
    n = store.list_calls
    client.get("/companies")
    assert store.list_calls == n


def test_comparison_read_through_pulls_once_then_serves_locally(world):
    client, store, settings, docs = world
    assert not (settings.published_dir / "ACME_2024_2025.json").exists()
    r = client.get("/comparison/ACME")
    assert r.status_code == 200 and r.json()["company"]["ticker"] == "ACME"
    saved = settings.published_dir / "ACME_2024_2025.json"
    assert saved.read_bytes() == docs["ACME"][1]  # byte-identical to the Volume file
    assert store.downloads == 1
    r2 = client.get("/comparison/ACME")
    assert r2.status_code == 200 and store.downloads == 1  # local hit now
    # and the local card no longer says remote
    cards = {c["ticker"]: c for c in client.get("/companies").json()["companies"]}
    assert cards["ACME"]["source"] == "local" and cards["ACME"]["published_by"] == "bob"


def test_local_hit_never_touches_the_store(world):
    client, store, _, _ = world
    store.offline = True
    r = client.get("/comparison/TEST")
    assert r.status_code == 200 and store.downloads == 0


def test_tampered_remote_report_is_rejected(world):
    client, store, settings, docs = world
    comp, data = docs["ACME"]
    bad = json.loads(data)
    bad["changes"][0]["title"] = "FIXTURE: edited in the volume"
    store.files[store.rows[1]["volume_path"]] = canonical_json(
        Comparison.model_validate(bad)
    ).encode()
    r = client.get("/comparison/ACME")
    assert r.status_code == 404
    assert not (settings.published_dir / "ACME_2024_2025.json").exists()
    assert "Traceback" not in r.text


def test_unknown_ticker_is_404(world):
    client, _, _, _ = world
    assert client.get("/comparison/ZZZZ").status_code == 404


def test_offline_store_keeps_local_reports_and_reports_offline(tmp_path):
    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    comp, data = make_doc("TEST")
    (settings.published_dir / "TEST_2024_2025.json").write_bytes(data)
    store = FakeStore([], {}, offline=True)
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as client:
        assert client.get("/store/health").json() == {"remote": "offline"}
        cards = client.get("/companies").json()["companies"]
        assert [c["ticker"] for c in cards] == ["TEST"] and cards[0]["published_by"] is None
        assert client.get("/comparison/TEST").status_code == 200
        assert client.get("/comparison/ACME").status_code == 404
        t = client.get("/trends").json()
        assert t["available"] is False and t["remote"] == "offline"


def test_disabled_store(tmp_path):
    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    comp, data = make_doc("TEST")
    (settings.published_dir / "TEST_2024_2025.json").write_bytes(data)

    def factory():
        raise StoreDisabled("not configured")

    app = api_main.create_app(settings, store_factory=factory)
    with TestClient(app) as client:
        assert client.get("/store/health").json() == {"remote": "disabled"}
        assert [c["ticker"] for c in client.get("/companies").json()["companies"]] == ["TEST"]
        assert client.get("/comparison/TEST").status_code == 200
        t = client.get("/trends").json()
        assert t == {
            "available": False,
            "remote": "disabled",
            "companies": 0,
            "by_category": [],
            "by_kind": [],
        }


def test_health_ok_and_cached(world):
    client, store, _, _ = world
    assert client.get("/store/health").json() == {"remote": "ok"}
    store.offline = True  # cached answer for HEALTH_TTL_SECONDS
    assert client.get("/store/health").json() == {"remote": "ok"}


def test_trends_returns_aggregates(world):
    client, store, _, _ = world
    store.trend_rows = {
        "by_category": [
            {"category": "geopolitical", "change_type": "new", "companies": 2},
            {
                "category": "geopolitical",
                "change_type": "largely_unchanged",
                "companies": 9,
            },  # filtered by SQL; ignored if present
            {"category": "credit", "change_type": "expanded", "companies": 1},
        ],
        "by_kind": [
            {
                "ticker": "ACME",
                "company_name": "FIXTURE: Acme",
                "kind": "new_risk",
                "highlights": 1,
            },
            {
                "ticker": "TEST",
                "company_name": "FIXTURE: Test",
                "kind": "potential_became_actual",
                "highlights": 2,
            },
        ],
    }
    t = client.get("/trends").json()
    assert t["available"] is True and t["remote"] == "ok" and t["companies"] == 2
    assert {r["change_type"] for r in t["by_category"]} == {"new", "expanded", "largely_unchanged"}
    assert t["by_kind"][1] == {
        "ticker": "TEST",
        "company_name": "FIXTURE: Test",
        "kind": "potential_became_actual",
        "highlights": 2,
    }


def test_merge_prefers_the_current_remote_analysis_for_the_same_filings():
    local_comp, local_bytes = make_doc("TEST")
    newer_comp, newer_bytes = make_doc("TEST", fingerprint="2" * 64)
    local = [
        {
            **json.loads(
                json.dumps(
                    {
                        "ticker": "TEST",
                        "name": "x",
                        "cik": "0000000000",
                        "old_fiscal_year": 2024,
                        "new_fiscal_year": 2025,
                        "old_filing_date": "",
                        "new_filing_date": "",
                        "total_changes": 1,
                        "by_change_type": {},
                        "max_score": 1,
                        "is_fixture": False,
                        "file": "TEST_2024_2025.json",
                    }
                )
            ),
            "analysis_id": local_comp.analysis_id,
            "old_accession": "a",
            "new_accession": "b",
            "published_by": None,
            "published_at": None,
            "source": "local",
        }
    ]
    cards, stale = api_main.merge_library(local, [row_for(newer_comp, newer_bytes, by="dana")])
    assert len(cards) == 1 and cards[0]["analysis_id"] == newer_comp.analysis_id
    assert (
        cards[0]["source"] == "remote"
        and stale
        and stale[0]["analysis_id"] == newer_comp.analysis_id
    )
    # an older remote pair never displaces a newer local pair
    older = row_for(newer_comp, newer_bytes)
    older["old_fiscal_year"], older["new_fiscal_year"] = 2022, 2023
    cards, stale = api_main.merge_library(local, [older])
    assert cards[0]["analysis_id"] == local_comp.analysis_id and not stale
