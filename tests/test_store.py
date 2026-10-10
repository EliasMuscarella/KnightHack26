"""Databricks store (D1): settings/allowlist, upload path, download verification, parameterized
execute, retries, health. Everything runs against a fake SDK client; no network."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.config import DatabricksSettings, validate_databricks_host
from pipeline.errors import ConfigError, DisallowedHost
from pipeline.schema import Comparison, canonical_json
from pipeline.store import (
    DatabricksStore,
    StoreAuthError,
    StoreDisabled,
    StoreIntegrityError,
    StoreNotFound,
    StoreQueryError,
    StoreUnavailable,
    recompute_analysis_id,
    tables,
    verify_report,
    volume_path,
)

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://adb-1234567890123456.7.azuredatabricks.net"


def settings(**kw) -> DatabricksSettings:
    base = dict(host=HOST, token="dapi-test-token", warehouse_id="abc123def456")
    base.update(kw)
    return DatabricksSettings(**base)


def real_doc() -> dict:
    """A non-fixture Comparison whose analysis_id recomputes: the contract fixture with the fixture
    flag cleared, a real ticker and a freshly computed id (strings stay FIXTURE-prefixed)."""
    d = json.loads((ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_text())
    d["is_fixture"] = False
    d["company"]["ticker"] = "TEST"
    comp = Comparison.model_validate(d)
    d["analysis_id"] = recompute_analysis_id(comp)
    return d


def real_bytes(d: dict | None = None) -> bytes:
    return canonical_json(Comparison.model_validate(d or real_doc())).encode("utf-8")


# ---------- fake SDK ----------


class FakeFiles:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.uploads = 0
        self.dirs: list[str] = []

    def create_directory(self, path):
        self.dirs.append(path)

    def upload(self, path, contents, *, overwrite=None):
        self.uploads += 1
        self.store[path] = contents.read()

    def get_metadata(self, path):
        from databricks.sdk.errors import NotFound

        if path not in self.store:
            raise NotFound("no such file")
        return SimpleNamespace(content_length=len(self.store[path]))

    def download(self, path):
        from databricks.sdk.errors import NotFound

        if path not in self.store:
            raise NotFound("no such file")
        return SimpleNamespace(contents=io.BytesIO(self.store[path]))


def response(rows=None, columns=None, state="SUCCEEDED", statement_id="st-1", error=None):
    from databricks.sdk.service.sql import StatementState

    manifest = None
    if columns:
        manifest = SimpleNamespace(
            schema=SimpleNamespace(
                columns=[
                    SimpleNamespace(name=n, type_name=SimpleNamespace(value=t)) for n, t in columns
                ]
            )
        )
    return SimpleNamespace(
        statement_id=statement_id,
        status=SimpleNamespace(state=StatementState(state), error=error),
        manifest=manifest,
        result=SimpleNamespace(data_array=rows or [], next_chunk_index=None),
    )


class FakeStatements:
    """Records every statement; `handler(sql, params) -> response` decides what comes back."""

    def __init__(self, handler=None):
        self.calls: list[tuple[str, dict]] = []
        self.handler = handler or (lambda sql, params: response())

    def execute_statement(self, *, statement, warehouse_id, parameters=None, **kw):
        params = {p.name: (p.value, p.type) for p in (parameters or [])}
        self.calls.append((statement, params))
        return self.handler(statement, params)

    def get_statement(self, statement_id):
        return response(statement_id=statement_id)

    def cancel_execution(self, statement_id):
        pass


class FakeClient:
    def __init__(self, handler=None):
        self.files = FakeFiles()
        self.statement_execution = FakeStatements(handler)
        self.current_user = SimpleNamespace(me=lambda: SimpleNamespace(user_name="t@example.com"))
        self.warehouses = SimpleNamespace(
            get=lambda wid: SimpleNamespace(state=SimpleNamespace(value="RUNNING"))
        )


def store(handler=None, **kw) -> tuple[DatabricksStore, FakeClient]:
    fake = FakeClient(handler)
    return DatabricksStore(settings(**kw), client=fake, sleep=lambda s: None), fake


# ---------- settings + allowlist ----------


def test_disabled_without_env(monkeypatch):
    for v in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"):
        monkeypatch.delenv(v, raising=False)
    from pipeline.config import get_databricks_settings

    s = get_databricks_settings()
    assert (
        not s.enabled and s.catalog == "riskdiff" and s.schema == "main" and s.volume == "reports"
    )
    with pytest.raises(StoreDisabled):
        DatabricksStore(s)
    assert "token" in s.redacted() and s.redacted()["token"] == "MISSING"


def test_host_validation():
    assert (
        validate_databricks_host("https://dbc-abc.cloud.databricks.com/")
        == "https://dbc-abc.cloud.databricks.com"
    )
    for bad in (
        "http://dbc-abc.cloud.databricks.com",
        "https://example.com",
        "https://dbc-abc.cloud.databricks.com.evil.net",
        "https://dbc-abc.cloud.databricks.com/api/2.0",
        "",
    ):
        with pytest.raises(ConfigError):
            validate_databricks_host(bad)


def test_identifiers_are_validated(monkeypatch):
    from pipeline.config import get_databricks_settings

    monkeypatch.setenv("DATABRICKS_CATALOG", "risk;DROP TABLE x")
    with pytest.raises(ConfigError):
        get_databricks_settings()


def test_allowlist_admits_only_the_configured_workspace(monkeypatch):
    from pipeline.http import check_host

    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    with pytest.raises(DisallowedHost):
        check_host(HOST + "/api/2.0/sql/statements")
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    assert check_host(HOST + "/api/2.0/sql/statements") == HOST.removeprefix("https://")
    with pytest.raises(DisallowedHost):  # another workspace on the same domain is still refused
        check_host("https://adb-999.9.azuredatabricks.net/api")
    with pytest.raises(DisallowedHost):
        check_host("https://example.com/")
    assert check_host("https://www.sec.gov/x") == "www.sec.gov"  # unchanged for everything else


def test_store_refuses_a_host_off_the_allowlist(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    # settings say one host, the environment allowlist another (none): the store must not talk to it
    with pytest.raises(DisallowedHost):
        DatabricksStore(settings(host="https://adb-1.2.azuredatabricks.net"), client=FakeClient())


# ---------- upload / download ----------


def test_upload_path_and_byte_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    data = real_bytes()
    comp = Comparison.model_validate_json(data)
    p = tmp_path / "TEST_2024_2025.json"
    p.write_bytes(data)
    st, fake = store()
    path = st.upload_report(p)
    assert path == f"/Volumes/riskdiff/main/reports/TEST/{comp.analysis_id}.json"
    assert path == volume_path(st.settings, "TEST", comp.analysis_id)
    assert fake.files.store[path] == data  # byte-for-byte
    assert fake.files.dirs == ["/Volumes/riskdiff/main/reports/TEST"]
    # same file again: no second upload
    assert st.upload_report(p) == path
    assert fake.files.uploads == 1


def test_upload_refuses_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    fx = ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json"
    st, _ = store()
    with pytest.raises(StoreIntegrityError):
        st.upload_report(fx)


def test_download_verifies_contract_and_analysis_id(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    d = real_doc()
    data = real_bytes(d)
    aid = d["analysis_id"]
    path = f"/Volumes/riskdiff/main/reports/TEST/{aid}.json"

    import hashlib

    cols = [("volume_path", "STRING"), ("ticker", "STRING"), ("content_sha256", "STRING")]

    def handler(sql, params):
        assert sql.startswith(
            "SELECT volume_path, ticker, content_sha256 FROM `riskdiff`.`main`.`reports`"
        )
        assert params["analysis_id"] == (aid, "STRING")
        return response([[path, "TEST", hashlib.sha256(data).hexdigest()]], cols)

    st, fake = store(handler)
    fake.files.store[path] = data
    comp, raw = st.download_report(aid)
    assert raw == data and comp.analysis_id == aid

    # tampered content (a title edited after publishing) -> bytes no longer match the recorded hash
    tampered = json.loads(data)
    tampered["changes"][0]["title"] = "FIXTURE: edited after the fact"
    fake.files.store[path] = canonical_json(Comparison.model_validate(tampered)).encode()
    with pytest.raises(StoreIntegrityError):
        st.download_report(aid)

    # a forged file that claims the requested id but was produced from other inputs: caught by
    # the analysis_id recomputation even when no content hash is known
    forged = json.loads(data)
    forged["code_fingerprint"] = "0" * 64
    fake.files.store[path] = canonical_json(Comparison.model_validate(forged)).encode()
    with pytest.raises(StoreIntegrityError):
        st.download_report(aid, volume_path=path)

    # not JSON at all
    fake.files.store[path] = b"<html>nope</html>"
    with pytest.raises(StoreIntegrityError):
        st.download_report(aid)

    # unknown id
    st2, _ = store(lambda sql, params: response([], cols))
    with pytest.raises(StoreNotFound):
        st2.download_report("f" * 64)

    # a path outside the Volume is never followed
    st3, _ = store(lambda sql, params: response([["/Volumes/other/x/y.json", "TEST", None]], cols))
    with pytest.raises(StoreIntegrityError):
        st3.download_report(aid)


def test_verify_report_rejects_fixture_and_wrong_id():
    fx = (ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_bytes()
    with pytest.raises(StoreIntegrityError):
        verify_report(fx)
    d = real_doc()
    with pytest.raises(StoreIntegrityError):
        verify_report(real_bytes(d), "a" * 64)
    assert verify_report(real_bytes(d), d["analysis_id"]).company.ticker == "TEST"


# ---------- execute / retries / health ----------


def test_execute_is_parameterized_and_typed(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)

    def handler(sql, params):
        assert params == {
            "s": ("x", "STRING"),
            "n": ("3", "BIGINT"),
            "b": ("true", "BOOLEAN"),
            "f": ("1.5", "DOUBLE"),
            "z": (None, "STRING"),
        }
        return response(
            [["7", "true", "a", None]],
            [("n", "INT"), ("b", "BOOLEAN"), ("s", "STRING"), ("z", "STRING")],
        )

    st, fake = store(handler)
    rows = st.execute(
        "SELECT :s, :n, :b, :f, :z", {"s": "x", "n": 3, "b": True, "f": 1.5, "z": None}
    )
    assert rows == [{"n": 7, "b": True, "s": "a", "z": None}]
    assert fake.statement_execution.calls[0][0] == "SELECT :s, :n, :b, :f, :z"
    with pytest.raises(TypeError):  # structured values must be passed as JSON text
        st.execute("SELECT :x", {"x": ["list"]})


def test_execute_failure_is_a_typed_error(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    st, _ = store(
        lambda sql, params: response(
            state="FAILED", error=SimpleNamespace(message="TABLE_OR_VIEW_NOT_FOUND")
        )
    )
    with pytest.raises(StoreQueryError) as ei:
        st.execute("SELECT 1")
    assert "TABLE_OR_VIEW_NOT_FOUND" in str(ei.value)


def test_retries_then_unavailable(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    import requests

    attempts = {"n": 0}

    def handler(sql, params):
        attempts["n"] += 1
        raise requests.ConnectionError("connection refused")

    sleeps: list[float] = []
    fake = FakeClient(handler)
    st = DatabricksStore(settings(), client=fake, sleep=sleeps.append)
    with pytest.raises(StoreUnavailable):
        st.execute("SELECT 1")
    assert attempts["n"] == 3 and len(sleeps) == 2  # 1 call + 2 retries, backoff between


def test_auth_errors_do_not_retry(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    from databricks.sdk.errors import PermissionDenied

    attempts = {"n": 0}

    def handler(sql, params):
        attempts["n"] += 1
        raise PermissionDenied("nope")

    st, _ = store(handler)
    with pytest.raises(StoreAuthError) as ei:
        st.execute("SELECT 1")
    assert attempts["n"] == 1 and "dapi" not in str(ei.value)


def test_health(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", HOST)
    st, fake = store()
    assert st.health()["remote"] == "ok" and st.health()["warehouse_state"] == "RUNNING"
    import requests

    fake.current_user = SimpleNamespace(
        me=lambda: (_ for _ in ()).throw(requests.ConnectionError("x"))
    )
    with pytest.raises(StoreUnavailable):
        st.health()


# ---------- tables ----------


def test_ddl_is_idempotent_statements_only():
    stmts = ddl_list = tables.ddl(settings())
    labels = [label for label, _ in stmts]
    assert labels == [
        "schema",
        "volume",
        "reports",
        "changes",
        "highlights",
        "topic_mentions",
        "category_activity",
    ]
    assert all("IF NOT EXISTS" in sql for _, sql in ddl_list)
    assert "CREATE CATALOG" not in " ".join(sql for _, sql in ddl_list)


def test_rows_cover_every_column_and_merge_is_parameterized():
    comp = Comparison.model_validate(real_doc())
    from datetime import UTC, datetime

    r = tables.report_row(
        comp,
        volume_path="/Volumes/riskdiff/main/reports/TEST/x.json",
        content_sha256="0" * 64,
        published_by="tester",
        published_at=datetime(2026, 10, 10, tzinfo=UTC),
    )
    assert set(r) == {n for n, _ in tables.REPORT_COLUMNS}
    assert r["n_new"] == comp.summary.by_change_type["new"] and r["is_current"] is True
    ch = tables.change_rows(comp)
    assert len(ch) == len(comp.changes) and set(ch[0]) == {n for n, _ in tables.CHANGE_COLUMNS}
    hl = tables.highlight_rows(comp)
    assert len(hl) == len(comp.highlights) and set(hl[0]) == {
        n for n, _ in tables.HIGHLIGHT_COLUMNS
    }
    assert all(h["new_text"] or h["old_text"] for h in hl)
    for t in tables.TABLES:
        sql = tables.merge_sql(settings(), t)
        assert (
            ":rows" in sql and "WHEN NOT MATCHED THEN INSERT *" in sql and "WHEN MATCHED" not in sql
        )
        assert "'" not in sql.replace(
            f"'{tables.struct_schema(tables.COLUMNS[t])}'", ""
        )  # no inline values
