"""Shared report store (Databricks). Optional at runtime: with no DATABRICKS_* variables set the
rest of RiskDiff behaves exactly as before. See databricks.py for the client wrapper, tables.py for
the derived Delta tables and publisher.py for the publish step."""

from pipeline.store.databricks import (
    DatabricksStore,
    StoreAuthError,
    StoreDisabled,
    StoreError,
    StoreIntegrityError,
    StoreNotFound,
    StoreQueryError,
    StoreTimeout,
    StoreUnavailable,
    recompute_analysis_id,
    verify_report,
    volume_path,
)

__all__ = [
    "DatabricksStore",
    "StoreAuthError",
    "StoreDisabled",
    "StoreError",
    "StoreIntegrityError",
    "StoreNotFound",
    "StoreQueryError",
    "StoreTimeout",
    "StoreUnavailable",
    "recompute_analysis_id",
    "verify_report",
    "volume_path",
]
