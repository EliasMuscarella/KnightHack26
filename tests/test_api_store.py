"""D4/D6/T9: the API against a fake shared store: library merge, read-through cache (local hit,
remote hit, remote offline), integrity rejection, the four health states and stale-while-revalidate
trends."""

from __future__ import annotations

import hashlib
import json
import threading
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
        self.gate: threading.Event | None = None  # when set, every call blocks until it opens
        self.warehouse_state = "RUNNING"
        self.warehouse_ready = threading.Event()  # statements block until the warehouse runs
        self.warehouse_ready.set()
        self.health_calls = 0
        self.downloads = 0
        self.list_calls = 0
        self.settings = type("S", (), {"table": lambda self, n: f"`riskdiff`.`main`.`{n}`"})()
        self.trend_rows: dict[str, list[dict]] = {}

    def _check(self):
        if self.gate is not None:
            self.gate.wait(10)
        if self.offline:
            raise StoreUnavailable("Databricks unreachable after 3 attempts (ConnectionError)")

    def _statement(self):
        self.warehouse_ready.wait(10)
        self._check()

    def list_reports(self):
        self._statement()
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
        self.health_calls += 1
        self._check()
        return {"remote": "ok", "warehouse_state": self.warehouse_state}

    def execute(self, sql, params=None):
        self._statement()
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
        assert client.get("/store/health").json() == {"remote": "offline", "warehouse_state": None}
        cards = client.get("/companies").json()["companies"]
        assert [c["ticker"] for c in cards] == ["TEST"] and cards[0]["published_by"] is None
        assert client.get("/comparison/TEST").status_code == 200
        assert client.get("/comparison/ACME").status_code == 404
        t = client.get("/trends").json()
        # offline with no remote result: the local aggregate, labelled as such
        assert t["status"] == "offline" and t["source"] == "local"
        assert [c["ticker"] for c in t["companies"]] == ["TEST"]


def test_disabled_store(tmp_path):
    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    comp, data = make_doc("TEST")
    (settings.published_dir / "TEST_2024_2025.json").write_bytes(data)

    def factory():
        raise StoreDisabled("not configured")

    app = api_main.create_app(settings, store_factory=factory)
    with TestClient(app) as client:
        assert client.get("/store/health").json() == {
            "remote": "disabled",
            "warehouse_state": None,
        }
        assert [c["ticker"] for c in client.get("/companies").json()["companies"]] == ["TEST"]
        assert client.get("/comparison/TEST").status_code == 200
        t = client.get("/trends").json()
        assert t["status"] == "disabled" and t["source"] == "local"
        assert t["computed_at"].endswith("Z")
        assert [c["ticker"] for c in t["companies"]] == ["TEST"]


def test_health_ok_and_cached(world):
    client, store, _, _ = world
    for _ in range(50):  # the startup check runs in the background
        if client.get("/store/health").json()["remote"] == "ok":
            break
        time.sleep(0.02)
    assert client.get("/store/health").json() == {"remote": "ok", "warehouse_state": "RUNNING"}
    store.offline = True  # cached answer for HEALTH_TTL_SECONDS
    assert client.get("/store/health").json()["remote"] == "ok"


def test_trends_from_the_store_once_refreshed(world):
    client, store, _, _ = world
    t = wait_for_trends(client, lambda t: t["source"] == "databricks")
    assert t["status"] == "ok" and t["computed_at"].endswith("Z")
    assert [c["ticker"] for c in t["companies"]] == ["ACME", "TEST"]
    assert t["headline"]["companies"] == 2


def wait_for_trends(client, pred, timeout: float = 5.0) -> dict:
    t0 = time.monotonic()
    while True:
        t = client.get("/trends").json()
        if pred(t) or time.monotonic() - t0 > timeout:
            return t
        time.sleep(0.02)


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


# ---------- T9: health states and stale-while-revalidate trends ----------


def gated_world(tmp_path, *, local: bool = True):
    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    rows, files = [], {}
    if local:
        comp, data = make_doc("TEST")
        (settings.published_dir / "TEST_2024_2025.json").write_bytes(data)
    acme, acme_bytes = make_doc("ACME")
    rows.append(row_for(acme, acme_bytes, by="bob"))
    files[rows[0]["volume_path"]] = acme_bytes
    store = FakeStore(rows, files)
    store.gate = threading.Event()  # closed: the first check / client build is still pending
    return settings, store


def test_health_is_connecting_while_the_first_check_is_pending(tmp_path):
    settings, store = gated_world(tmp_path)
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as client:
        for _ in range(3):  # however often it is asked, a pending check is never "offline"
            h = client.get("/store/health").json()
            assert h == {"remote": "connecting", "warehouse_state": None}
        store.gate.set()
        for _ in range(100):
            h = client.get("/store/health").json()
            if h["remote"] != "connecting":
                break
            time.sleep(0.02)
        assert h == {"remote": "ok", "warehouse_state": "RUNNING"}


def test_health_connecting_while_the_warehouse_starts_then_offline_only_after_a_failure(tmp_path):
    settings, store = gated_world(tmp_path)
    store.gate = None
    store.warehouse_state = "STARTING"
    store.warehouse_ready.clear()
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as client:
        for _ in range(5):
            h = client.get("/store/health").json()
            assert h["remote"] == "connecting"
        assert h["warehouse_state"] == "STARTING"
        # a real failure (after the store's retries) is what makes it offline
        store.offline = True
        lib = app.state.rd.remote
        lib._check_health()
        assert client.get("/store/health").json()["remote"] == "offline"
        store.warehouse_ready.set()


def test_trends_cold_start_serves_local_while_connecting(tmp_path):
    """The reported bug: the first /trends after a restart must not say 'not connected'."""
    settings, store = gated_world(tmp_path)
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as client:
        t0 = time.monotonic()
        t = client.get("/trends").json()
        assert time.monotonic() - t0 < 2.0
        assert t["status"] == "connecting" and t["source"] == "local"
        assert [c["ticker"] for c in t["companies"]] == ["TEST"]
        store.gate.set()  # the warehouse answers: the background refresh lands
        t = wait_for_trends(client, lambda t: t["source"] == "databricks")
        assert t["status"] == "ok" and [c["ticker"] for c in t["companies"]] == ["ACME"]


def test_trends_connecting_with_nothing_local_is_an_empty_retryable_answer(tmp_path):
    settings, store = gated_world(tmp_path, local=False)
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as client:
        r = client.get("/trends")
        assert r.status_code == 200
        t = r.json()
        assert t == {
            "status": "connecting",
            "source": None,
            "computed_at": None,
            "companies": [],
            "headline": {"companies": 0, "meaningful_changes": 0, "top_topic": None},
            "topics": [],
            "category_activity": [],
            "potential_to_actual": [],
            "change_mix": [],
        }
        store.gate.set()


def test_trends_stale_while_revalidate_and_disk_cache_survives_restart(tmp_path):
    settings, store = gated_world(tmp_path)
    store.gate.set()
    app = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app) as client:
        first = wait_for_trends(client, lambda t: t["source"] == "databricks")
        assert first["source"] == "databricks"
    cache = settings.cache_dir / "trends" / "trends.json"
    assert cache.exists()

    # a new app instance (API restart) with a store that hangs: the disk result is served at once
    store.gate = threading.Event()
    app2 = api_main.create_app(settings, store_factory=lambda: store)
    with TestClient(app2) as client:
        t0 = time.monotonic()
        t = client.get("/trends").json()
        assert time.monotonic() - t0 < 1.0  # no wait on the store (target 300 ms, measured live)
        assert t["source"] == "databricks" and t["computed_at"] == first["computed_at"]
        assert t["status"] == "connecting"  # the store state now, not when it was computed
        # make the cached result stale: the next call still answers instantly and refreshes behind
        svc = app2.state.rd.trends
        svc._remote_entry["epoch"] = 0.0
        t0 = time.monotonic()
        t = client.get("/trends").json()
        assert time.monotonic() - t0 < 1.0  # no wait on the store (target 300 ms, measured live)
        assert t["computed_at"] == first["computed_at"]
        assert svc._thread is not None and svc._thread.is_alive()  # revalidating
        store.gate.set()
        svc._thread.join(5)
        t = client.get("/trends").json()
        assert t["source"] == "databricks" and t["computed_at"] >= first["computed_at"]


def test_trends_never_5xx(tmp_path, monkeypatch):
    settings, store = gated_world(tmp_path)
    store.gate.set()
    app = api_main.create_app(settings, store_factory=lambda: store)

    def boom():
        raise RuntimeError("secret-ish detail that must not leak")

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.rd.trends, "get", boom)
        r = client.get("/trends")
        assert r.status_code == 200 and "secret" not in r.text and "Traceback" not in r.text
        assert r.json()["source"] is None and r.json()["companies"] == []


# ---------- T11: the /trends response on the real reports (Databricks disabled) ----------

COMPANY_KEYS = {
    "ticker",
    "name",
    "analysis_id",
    "cik",
    "old_accession",
    "new_accession",
    "edgar_url_old",
    "edgar_url_new",
    "old_fiscal_year",
    "new_fiscal_year",
    "total_changes",
    "meaningful_changes",
    "by_change_type",
}


def test_trends_local_fallback_shape_and_timing(tmp_path):
    import shutil

    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    for p in sorted((ROOT / "data" / "published").glob("*_*_*.json")):
        shutil.copy(p, settings.published_dir / p.name)
    shutil.copytree(ROOT / "data" / "derived", settings.data_dir / "derived")

    def disabled():
        raise StoreDisabled("not configured")

    app = api_main.create_app(settings, store_factory=disabled)
    with TestClient(app) as client:
        app.state.rd.trends._local_entry = None  # measure a real recompute (warm-up may have run)
        t0 = time.monotonic()
        t = client.get("/trends").json()
        assert time.monotonic() - t0 < 2.0  # local recompute for two reports
        t0 = time.monotonic()
        again = client.get("/trends").json()
        assert time.monotonic() - t0 < 1.0  # served from cache (target 300 ms, measured live)
        assert again == t
    assert set(t) == {
        "status",
        "source",
        "computed_at",
        "companies",
        "headline",
        "topics",
        "category_activity",
        "potential_to_actual",
        "change_mix",
    }
    assert t["status"] == "disabled" and t["source"] == "local"
    assert [c["ticker"] for c in t["companies"]] == ["NVDA", "SF"]
    assert all(set(c) == COMPANY_KEYS for c in t["companies"])
    assert set(t["headline"]) == {"companies", "meaningful_changes", "top_topic"}
    for topic in t["topics"]:
        assert set(topic) == {
            "topic",
            "source",
            "company_count",
            "sentence_count",
            "companies",
            "examples",
        }
        assert topic["source"] in ("lexicon", "entity", "phrase")
        assert len(topic["examples"]) == topic["company_count"]
    keys = [(-x["company_count"], -x["sentence_count"], x["topic"].casefold()) for x in t["topics"]]
    assert keys == sorted(keys)
    for row in t["category_activity"]:
        assert set(row) == {
            "ticker",
            "category",
            "risk_factors",
            "change_ids",
            "added_sentences",
            "removed_sentences",
            "modified_sentences",
            "added_words",
            "removed_words",
            "modified_words",
            "max_score",
        }
    for row in t["potential_to_actual"]:
        assert set(row) == {
            "ticker",
            "company_name",
            "change_id",
            "short_title",
            "old_sentence_id",
            "new_sentence_id",
            "old_text",
            "new_text",
            "score",
        }
    assert [m["ticker"] for m in t["change_mix"]] == ["NVDA", "SF"]
    # the disk cache survives a new app instance
    app2 = api_main.create_app(settings, store_factory=disabled)
    with TestClient(app2) as client:
        assert client.get("/trends").json()["computed_at"] == t["computed_at"]


def test_trends_local_derives_missing_files(tmp_path):
    import shutil

    settings = settings_for(tmp_path)
    settings.published_dir.mkdir(parents=True)
    p = ROOT / "data" / "published" / "SF_2024_2025.json"
    shutil.copy(p, settings.published_dir / p.name)

    def disabled():
        raise StoreDisabled("not configured")

    app = api_main.create_app(settings, store_factory=disabled)
    with TestClient(app) as client:
        t = client.get("/trends").json()
    assert [c["ticker"] for c in t["companies"]] == ["SF"] and t["topics"]
    derived = list((settings.data_dir / "derived").glob("*.trends.json"))
    assert len(derived) == 1
    assert derived[0].read_bytes() == (ROOT / "data" / "derived" / derived[0].name).read_bytes()
