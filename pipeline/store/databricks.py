"""Thin wrapper around the official `databricks-sdk` (pinned in pyproject.toml).

Two Databricks APIs are used, both through the SDK:
  * Files API            -> byte-for-byte upload/download of published JSON in a Unity Catalog Volume
  * Statement Execution  -> parameterized SQL against a SQL warehouse (Delta tables derived from the JSON)

Rules enforced here:
  * the workspace host comes from DATABRICKS_HOST, must validate (https, known Databricks domain)
    and is checked against the outbound allowlist (`pipeline.http.check_host`) before any call;
  * every SQL statement is parameterized (`:name` markers + typed parameters); table names are
    code constants; nothing from user input is ever interpolated into SQL;
  * timeouts on every call, at most MAX_RETRIES retries with backoff for transient failures, and
    typed errors (StoreUnavailable, StoreAuthError, StoreNotFound, StoreQueryError,
    StoreIntegrityError, StoreTimeout) that never carry the token;
  * a downloaded report is returned only after it validates against the contract, its
    `analysis_id` recomputes from the file's own recorded fields (`verify_report`) and, when the
    `reports` row is known, its bytes hash to the `content_sha256` recorded at publish time
    (analysis_id covers the analysis INPUTS, the content hash covers the bytes).
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pipeline.config import DatabricksSettings, get_databricks_settings
from pipeline.errors import PipelineError
from pipeline.http import check_host
from pipeline.schema import Comparison

log = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = 30  # per HTTP request inside the SDK
SDK_RETRY_BUDGET_SECONDS = 20  # the SDK's own retry budget per call (kept short; we retry above it)
MAX_RETRIES = 2  # our retries on top: 1 call + 2 retries
BACKOFF_SECONDS = (0.5, 1.5)
STATEMENT_WAIT = "30s"  # synchronous wait inside execute_statement before we start polling
STATEMENT_TIMEOUT_SECONDS = 180.0  # total, including a cold warehouse start
POLL_SECONDS = 1.0


# ---------- errors ----------


class StoreError(PipelineError):
    code = "store"
    http_status = 503


class StoreDisabled(StoreError):
    code = "store_disabled"


class StoreUnavailable(StoreError):
    code = "store_unavailable"


class StoreAuthError(StoreError):
    code = "store_auth"


class StoreNotFound(StoreError):
    code = "store_not_found"
    http_status = 404


class StoreQueryError(StoreError):
    code = "store_query"
    http_status = 500


class StoreIntegrityError(StoreError):
    code = "store_integrity"
    http_status = 502


class StoreTimeout(StoreError):
    code = "store_timeout"


# ---------- pure helpers ----------


def volume_path(settings: DatabricksSettings, ticker: str, analysis_id: str) -> str:
    return f"{settings.volume_root}/{ticker}/{analysis_id}.json"


def recompute_analysis_id(comp: Comparison) -> str:
    """The id from the file's OWN recorded inputs (its pipeline/rubric versions, code fingerprint,
    model ids and accessions), i.e. the same payload `pipeline.score.analysis_id` hashes. A file
    produced by an older code version therefore still verifies; a tampered one does not."""
    m = comp.model_ids
    payload = "|".join(
        [
            comp.old_filing.accession_number,
            comp.new_filing.accession_number,
            comp.pipeline_version,
            comp.rubric_version,
            comp.code_fingerprint,
            m.embedding_model,
            m.embedding_backend,
            m.ner_model,
            m.category_method,
            m.sentence_splitter,
            m.llm_provider or "",
            m.llm_model or "",
            m.prompt_sha256 or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_report(data: bytes, expected_analysis_id: str | None = None) -> Comparison:
    """Contract validation + analysis_id recomputation. Fixture data is never accepted."""
    try:
        comp = Comparison.model_validate_json(data)
    except Exception as e:  # noqa: BLE001
        raise StoreIntegrityError(
            f"report does not validate against the contract: {type(e).__name__}"
        ) from e
    if comp.is_fixture or comp.company.ticker == "FIXTUR":
        raise StoreIntegrityError("fixture data is never accepted from the shared store")
    if expected_analysis_id and comp.analysis_id != expected_analysis_id:
        raise StoreIntegrityError("report carries a different analysis_id than requested")
    if recompute_analysis_id(comp) != comp.analysis_id:
        raise StoreIntegrityError("analysis_id does not recompute from the report's own fields")
    return comp


def _param_type(value: object) -> str:
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "BIGINT"
    if isinstance(value, float):
        return "DOUBLE"
    if value is None or isinstance(value, str):
        return "STRING"
    raise TypeError(
        f"unsupported SQL parameter type {type(value).__name__}; pass JSON text instead"
    )


def _param_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _coerce(value: str | None, type_name: str | None) -> Any:
    """JSON_ARRAY results arrive as strings; cast by the manifest's column type."""
    if value is None:
        return None
    t = (type_name or "").upper()
    try:
        if t in ("INT", "LONG", "SHORT", "BYTE", "BIGINT", "INTEGER", "SMALLINT", "TINYINT"):
            return int(value)
        if t in ("DOUBLE", "FLOAT", "DECIMAL"):
            return float(value)
        if t == "BOOLEAN":
            return value.lower() == "true"
    except ValueError:
        return value
    return value


# ---------- the store ----------


class DatabricksStore:
    """One instance per process. The SDK client is created lazily (first use) so that importing or
    constructing the store never touches the network; `client` is injectable for tests."""

    def __init__(
        self,
        settings: DatabricksSettings | None = None,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings or get_databricks_settings()
        if not self.settings.enabled:
            raise StoreDisabled(
                "Databricks is not configured (DATABRICKS_HOST, DATABRICKS_TOKEN and "
                "DATABRICKS_WAREHOUSE_ID are required)"
            )
        # SSRF guard: the configured workspace is the only host the allowlist admits for the SDK.
        check_host(self.settings.host or "")
        self._client = client
        self._sleep = sleep

    # -- client --

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._make_client()
        return self._client

    def _make_client(self) -> Any:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.core import Config

        class _Config(Config):
            # The SDK probes <host>/.well-known/databricks-config while building a Config. It is a
            # best-effort OAuth discovery call we never need (PAT auth) and it would block for the
            # whole retry budget when the workspace is unreachable; skip it.
            def _resolve_host_metadata(self) -> None:  # pragma: no cover - SDK internals
                return None

        cfg = _Config(
            host=self.settings.host,
            token=self.settings.token,
            auth_type="pat",
            http_timeout_seconds=HTTP_TIMEOUT_SECONDS,
            retry_timeout_seconds=SDK_RETRY_BUDGET_SECONDS,
        )
        return WorkspaceClient(config=cfg)

    # -- retry + error translation --

    def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        from databricks.sdk import errors as dbe

        retryable = (
            dbe.TemporarilyUnavailable,
            dbe.TooManyRequests,
            dbe.InternalError,
            dbe.DeadlineExceeded,
            dbe.OperationTimeout,
            dbe.ResourceExhausted,
            dbe.RequestLimitExceeded,
        )
        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except (dbe.Unauthenticated, dbe.PermissionDenied) as e:
                raise StoreAuthError("Databricks rejected the credentials or permissions") from e
            except (dbe.NotFound, dbe.ResourceDoesNotExist) as e:
                raise StoreNotFound(f"not found in the shared store: {_brief(e)}") from e
            except retryable as e:
                last = e
            except dbe.DatabricksError as e:
                raise StoreQueryError(f"Databricks error: {_brief(e)}") from e
            except TimeoutError as e:
                last = e
            except OSError as e:  # requests' ConnectionError/Timeout are IOError subclasses
                last = e
            if attempt < MAX_RETRIES:
                delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
                log.warning(
                    "Databricks call failed (%s), retry %d/%d in %.1fs",
                    type(last).__name__,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                self._sleep(delay)
        raise StoreUnavailable(
            f"Databricks unreachable after {MAX_RETRIES + 1} attempts ({type(last).__name__})"
        ) from last

    # -- Files API --

    def upload_report(self, path: Path) -> str:
        """Upload a published JSON byte-for-byte to
        /Volumes/{catalog}/{schema}/{volume}/{ticker}/{analysis_id}.json and return that path.
        Fixture data is refused. An identical file already in the Volume is left alone."""
        data = Path(path).read_bytes()
        comp = verify_report(data)
        target = volume_path(self.settings, comp.company.ticker, comp.analysis_id)
        if self._exists_with_size(target, len(data)):
            log.info("already in the shared store: %s", target)
            return target
        folder = target.rsplit("/", 1)[0]
        try:
            self._call(self.client.files.create_directory, folder)
        except StoreError as e:  # the directory may already exist; the upload below decides
            log.debug("create_directory(%s): %s", folder, e.message)
        self._call(self.client.files.upload, target, io.BytesIO(data), overwrite=True)
        log.info("uploaded %s (%d bytes)", target, len(data))
        return target

    def _exists_with_size(self, target: str, size: int) -> bool:
        try:
            meta = self._call(self.client.files.get_metadata, target)
        except StoreNotFound:
            return False
        return getattr(meta, "content_length", None) == size

    def download_report(
        self,
        analysis_id: str,
        *,
        volume_path: str | None = None,
        content_sha256: str | None = None,
    ) -> tuple[Comparison, bytes]:
        """Fetch a report by analysis_id (path and content hash looked up in `reports` unless
        given), validate it against the contract, verify that its analysis_id recomputes and that
        the bytes match the recorded hash. Returns (comparison, bytes)."""
        from pipeline.store import tables

        if volume_path is None:
            rows = self.execute(tables.path_for_sql(self.settings), {"analysis_id": analysis_id})
            if not rows:
                raise StoreNotFound(
                    f"no report with analysis_id {analysis_id[:12]}… in the shared store"
                )
            volume_path = str(rows[0]["volume_path"])
            content_sha256 = content_sha256 or rows[0].get("content_sha256")
        if not volume_path.startswith(self.settings.volume_root + "/"):
            raise StoreIntegrityError("report path is outside the configured Volume")
        resp = self._call(self.client.files.download, volume_path)
        data = resp.contents.read()
        if content_sha256 and hashlib.sha256(data).hexdigest() != content_sha256:
            raise StoreIntegrityError("report bytes do not match the hash recorded at publish time")
        comp = verify_report(data, analysis_id)
        return comp, data

    # -- SQL --

    def list_reports(self) -> list[dict]:
        """Current reports (one row per ticker + filing pair) from the `reports` table."""
        from pipeline.store import tables

        return self.execute(tables.list_current_sql(self.settings), {"current": True})

    def execute(
        self,
        sql: str,
        params: Mapping[str, object] | None = None,
        *,
        timeout: float = STATEMENT_TIMEOUT_SECONDS,
    ) -> list[dict]:
        """Run ONE parameterized statement on the warehouse and return rows as dicts (typed by the
        result manifest). `params` values must be str/int/float/bool/None; pass JSON text for
        anything structured and decode it in SQL (from_json)."""
        from databricks.sdk.service.sql import (
            Disposition,
            ExecuteStatementRequestOnWaitTimeout,
            Format,
            StatementParameterListItem,
            StatementState,
        )

        items = [
            StatementParameterListItem(name=k, value=_param_value(v), type=_param_type(v))
            for k, v in (params or {}).items()
        ]
        resp = self._call(
            self.client.statement_execution.execute_statement,
            statement=sql,
            warehouse_id=self.settings.warehouse_id,
            catalog=self.settings.catalog,
            schema=self.settings.schema,
            parameters=items or None,
            wait_timeout=STATEMENT_WAIT,
            on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CONTINUE,
            format=Format.JSON_ARRAY,
            disposition=Disposition.INLINE,
        )
        deadline = time.monotonic() + timeout
        while resp.status is not None and resp.status.state in (
            StatementState.PENDING,
            StatementState.RUNNING,
        ):
            if time.monotonic() > deadline:
                try:
                    self._call(self.client.statement_execution.cancel_execution, resp.statement_id)
                finally:
                    raise StoreTimeout(f"statement still running after {timeout:.0f}s")
            self._sleep(POLL_SECONDS)
            resp = self._call(self.client.statement_execution.get_statement, resp.statement_id)
        state = resp.status.state if resp.status is not None else None
        if state != StatementState.SUCCEEDED:
            err = getattr(resp.status, "error", None)
            msg = getattr(err, "message", None) or str(state)
            raise StoreQueryError(f"statement {str(state).rsplit('.', 1)[-1]}: {msg[:300]}")
        return self._rows(resp)

    def _rows(self, resp: Any) -> list[dict]:
        manifest = getattr(resp, "manifest", None)
        schema = getattr(manifest, "schema", None)
        columns = list(getattr(schema, "columns", None) or [])
        if not columns:
            return []
        names = [c.name for c in columns]
        types = [getattr(c, "type_name", None) for c in columns]
        types = [getattr(t, "value", t) for t in types]
        rows: list[list] = []
        result = getattr(resp, "result", None)
        while result is not None:
            rows.extend(result.data_array or [])
            nxt = getattr(result, "next_chunk_index", None)
            if nxt is None:
                break
            result = self._call(
                self.client.statement_execution.get_statement_result_chunk_n, resp.statement_id, nxt
            )
        return [
            {n: _coerce(v, t) for n, t, v in zip(names, types, row, strict=False)} for row in rows
        ]

    # -- health --

    def health(self) -> dict:
        """Reachability + credentials + warehouse state. Raises a StoreError when offline."""
        me = self._call(self.client.current_user.me)
        wh = self._call(self.client.warehouses.get, self.settings.warehouse_id)
        state = getattr(getattr(wh, "state", None), "value", None)
        return {
            "remote": "ok",
            "warehouse_state": state,
            "authenticated": bool(getattr(me, "user_name", None) or getattr(me, "id", None)),
        }


def _brief(e: Exception) -> str:
    return str(e).splitlines()[0][:200] if str(e) else type(e).__name__
