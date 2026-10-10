"""D3: remote publish step and sync script against a fake SDK with simulated Delta tables."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline.schema import Comparison, canonical_json
from pipeline.store import DatabricksStore, tables
from pipeline.store.publisher import publish_remote, publish_remote_if_enabled
from tests.test_store import HOST, FakeClient, real_doc, response, settings


class TableSim:
    """Applies the store's statements to in-memory tables: insert-if-absent MERGEs (rows come as
    the :rows JSON parameter), the is_current flip, and the SELECTs the publisher issues."""

    def __init__(self):
        self.rows: dict[str, dict[tuple, dict]] = {t: {} for t in tables.TABLES}
        self.statements: list[str] = []

    def __call__(self, sql, params):
        self.statements.append(sql.split("\n", 1)[0])
        m = re.match(r"MERGE INTO `riskdiff`\.`main`\.`(\w+)`", sql)
        if m:
            table = m.group(1)
            for row in json.loads(params["rows"][0]):
                key = tuple(row[k] for k in tables.KEYS[table])
                self.rows[table].setdefault(key, row)  # WHEN NOT MATCHED THEN INSERT
            return response()
        if sql.startswith("UPDATE `riskdiff`.`main`.`reports` SET is_current"):
            aid = params["analysis_id"][0]
            for row in self.rows["reports"].values():
                if (
                    row["ticker"] == params["ticker"][0]
                    and row["old_accession"] == params["old_accession"][0]
                    and row["new_accession"] == params["new_accession"][0]
                ):
                    row["is_current"] = row["analysis_id"] == aid
            return response()
        if sql.startswith("SELECT analysis_id FROM `riskdiff`.`main`.`reports`"):
            aid = params["analysis_id"][0]
            hit = [[aid]] if (aid,) in self.rows["reports"] else []
            return response(hit, [("analysis_id", "STRING")])
        raise AssertionError(f"unexpected statement: {sql[:80]}")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh1")


def write_report(tmp_path: Path, d: dict | None = None) -> tuple[Path, Comparison]:
    comp = Comparison.model_validate(d or real_doc())
    p = (
        tmp_path
        / f"{comp.company.ticker}_{comp.old_filing.fiscal_year}_{comp.new_filing.fiscal_year}.json"
    )
    p.write_text(canonical_json(comp), encoding="utf-8")
    return p, comp


def test_publish_uploads_merges_in_order_and_flips_current(tmp_path, env):
    sim = TableSim()
    fake = FakeClient(sim)
    store = DatabricksStore(settings(), client=fake, sleep=lambda s: None)
    p, comp = write_report(tmp_path)
    r = publish_remote(p, store, published_by="alice")
    assert r.inserted and r.made_current
    assert r.volume_path == f"/Volumes/riskdiff/main/reports/TEST/{comp.analysis_id}.json"
    assert fake.files.store[r.volume_path] == p.read_bytes()
    expected = [
        "SELECT analysis_id FROM `riskdiff`.`main`.`reports`",
        "MERGE INTO `riskdiff`.`main`.`reports`",
        "MERGE INTO `riskdiff`.`main`.`changes`",
        "MERGE INTO `riskdiff`.`main`.`highlights`",
        "UPDATE `riskdiff`.`main`.`reports` SET is_current",
    ]
    assert len(sim.statements) == len(expected)
    for got, want in zip(sim.statements, expected, strict=True):
        assert got.startswith(want), got
    rep = sim.rows["reports"][(comp.analysis_id,)]
    assert rep["published_by"] == "alice" and rep["is_current"] is True
    assert rep["content_sha256"] == __import__("hashlib").sha256(p.read_bytes()).hexdigest()
    assert len(sim.rows["changes"]) == len(comp.changes)
    assert len(sim.rows["highlights"]) == len(comp.highlights)


def test_second_publish_changes_nothing(tmp_path, env):
    sim = TableSim()
    fake = FakeClient(sim)
    store = DatabricksStore(settings(), client=fake, sleep=lambda s: None)
    p, comp = write_report(tmp_path)
    publish_remote(p, store, published_by="alice")
    import copy

    snapshot = copy.deepcopy(sim.rows)
    uploads = fake.files.uploads
    r = publish_remote(p, store, published_by="bob")  # another teammate syncs the same file
    assert not r.inserted and not r.made_current
    assert sim.rows == snapshot  # no row changed
    assert fake.files.uploads == uploads  # no second upload
    assert not any(s.startswith("UPDATE") for s in sim.statements[5:])  # no flip on repeat


def test_new_analysis_for_same_filings_becomes_current(tmp_path, env):
    sim = TableSim()
    store = DatabricksStore(settings(), client=FakeClient(sim), sleep=lambda s: None)
    p1, c1 = write_report(tmp_path)
    publish_remote(p1, store, published_by="alice")
    d2 = real_doc()
    d2["code_fingerprint"] = "1" * 64  # a code change -> new analysis_id for the same filings
    from pipeline.store import recompute_analysis_id

    d2["analysis_id"] = recompute_analysis_id(Comparison.model_validate(d2))
    (tmp_path / "v2").mkdir()
    p2, c2 = write_report(tmp_path / "v2", d2)
    publish_remote(p2, store, published_by="alice")
    assert c1.analysis_id != c2.analysis_id
    assert sim.rows["reports"][(c1.analysis_id,)]["is_current"] is False  # kept, not deleted
    assert sim.rows["reports"][(c2.analysis_id,)]["is_current"] is True
    # syncing the OLD file again does not flip current back
    publish_remote(p1, store, published_by="carol")
    assert sim.rows["reports"][(c2.analysis_id,)]["is_current"] is True


def test_publish_remote_if_enabled_statuses(tmp_path, monkeypatch):
    p, _ = write_report(tmp_path)
    for v in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(v, raising=False)
    assert publish_remote_if_enabled(p)["status"] == "disabled"
    assert publish_remote_if_enabled(p, enabled=False)["status"] == "skipped"
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.com")  # not a Databricks domain
    monkeypatch.setenv("DATABRICKS_TOKEN", "x")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "y")
    out = publish_remote_if_enabled(p)
    assert out["status"] == "failed" and "dapi" not in json.dumps(out)


def test_pipeline_remote_step_never_breaks_local_publish(tmp_path, env, monkeypatch):
    """A failing store (unreachable) leaves the local publish intact and reports failure."""
    import requests

    from pipeline.store import publisher

    def boom(sql, params):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(
        publisher,
        "DatabricksStore",
        lambda s: DatabricksStore(s, client=FakeClient(boom), sleep=lambda x: None),
    )
    p, _ = write_report(tmp_path)
    out = publish_remote_if_enabled(p)
    assert out["status"] == "failed" and out["code"] in ("store_unavailable", "store_not_found")
    assert p.exists()


def test_fixture_run_skips_remote_step(monkeypatch, tmp_path):
    """The synthetic fixture never reaches the shared store, even with Databricks configured."""
    monkeypatch.setenv("RISKDIFF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RISKDIFF_ALLOW_FIXTURE", "1")
    from pipeline.run import run_pipeline

    ctx = run_pipeline("FIXTUR", until_stage=8)
    assert "remote_publish" not in ctx.outputs


def test_sync_script_uses_the_same_path(tmp_path, env, monkeypatch):
    import importlib

    sync = importlib.import_module("scripts.sync_to_databricks")
    sim = TableSim()
    fake = FakeClient(sim)
    monkeypatch.setattr(
        sync, "DatabricksStore", lambda s: DatabricksStore(s, client=fake, sleep=lambda x: None)
    )
    p, comp = write_report(tmp_path)
    (tmp_path / "FIXTURE_comparison.json").write_text("{}")  # ignored: not TICKER_FY_FY.json
    assert sync.main([str(p)]) == 0
    assert (comp.analysis_id,) in sim.rows["reports"]
    assert sync.main([str(p)]) == 0  # second run: no-op, still ok
    assert fake.files.uploads == 1
