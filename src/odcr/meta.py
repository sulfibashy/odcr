"""Meta tables: created inside each platform, in its own SQL dialect.

All tables are append-only logs so history is never lost.
"""

from __future__ import annotations

from typing import Any

DEFAULT_META_SCHEMA = "odcr_meta"

TABLES: dict[str, list[tuple[str, str]]] = {
    "contracts": [
        ("contract_id", "name"), ("contract_version", "short"), ("name", "name"), ("domain", "name"),
        ("owner", "name"), ("yaml_hash", "id"), ("source_path", "text"), ("loaded_at", "ts"),
    ],
    "validation_runs": [
        ("run_id", "id"), ("contract_id", "name"), ("contract_version", "short"), ("object_name", "name"),
        ("batch_id", "name"), ("pipeline", "name"), ("stage", "name"), ("started_at", "ts"),
        ("finished_at", "ts"), ("status", "short"), ("checks_total", "int"), ("checks_failed", "int"),
        ("checks_warned", "int"), ("rows_checked", "int"), ("error_message", "text"),
    ],
    "check_results": [
        ("run_id", "id"), ("check_id", "name"), ("check_type", "short"), ("object_name", "name"),
        ("column_name", "name"), ("severity", "short"), ("expected", "text"), ("actual", "text"),
        ("status", "short"), ("message", "text"), ("query_text", "text"), ("created_at", "ts"),
    ],
    "quarantine_log": [
        ("run_id", "id"), ("contract_id", "name"), ("object_name", "name"), ("batch_id", "name"),
        ("reason", "text"), ("created_at", "ts"), ("released_at", "ts"),
    ],
    "notifications": [
        ("run_id", "id"), ("run_kind", "short"), ("channel", "short"), ("recipient", "text"),
        ("audience", "short"), ("status", "short"), ("message", "text"), ("sent_at", "ts"),
    ],
    "reconciliation_runs": [
        ("run_id", "id"), ("recon_id", "name"), ("source_object", "name"), ("target_object", "name"),
        ("batch_id", "name"), ("pipeline", "name"), ("started_at", "ts"), ("finished_at", "ts"),
        ("status", "short"), ("checks_total", "int"), ("checks_failed", "int"), ("error_message", "text"),
    ],
    "reconciliation_results": [
        ("run_id", "id"), ("check_id", "name"), ("check_type", "short"), ("column_name", "name"),
        ("source_value", "text"), ("target_value", "text"), ("difference", "text"), ("tolerance", "text"),
        ("status", "short"), ("message", "text"), ("created_at", "ts"),
    ],
    "pipeline_events": [
        ("event_id", "id"), ("pipeline", "name"), ("stage", "name"), ("stage_order", "int"),
        ("batch_id", "name"), ("mode", "short"), ("object_name", "name"), ("row_count", "int"),
        ("status", "short"), ("details", "text"), ("event_time", "ts"),
    ],
}


def ddl(adapter: Any, schema: str = DEFAULT_META_SCHEMA) -> list[str]:
    """The CREATE statements an SQL adapter runs for the meta tables (for docs and review)."""
    types = adapter.meta_types()
    out = []
    if not adapter.meta_in_current_schema:
        out.append(adapter.create_schema_sql(schema))
    for table, cols in TABLES.items():
        cols_sql = ", ".join(f"{adapter.quote(c)} {types[t]}" for c, t in cols)
        out.append(adapter.create_table_sql(adapter.meta_table(schema, table), cols_sql))
    return out


def ensure_meta(adapter: Any, schema: str = DEFAULT_META_SCHEMA) -> None:
    """Create the meta schema and tables if they do not exist (idempotent, any adapter)."""
    adapter.meta_ensure(schema)
