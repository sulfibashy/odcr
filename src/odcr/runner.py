"""Run a contract against a platform: schema checks, quality checks, meta logging, quarantine, notifications."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import notify
from .adapters.base import Adapter, UnsupportedCheck, type_matches
from .checks import Check, build_checks, compare, describe_expectation
from .config import Config
from .contract import Contract, SchemaObject

PASSED, FAILED, WARNING, ERROR, SKIPPED = "passed", "failed", "warning", "error", "skipped"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class CheckResult:
    check_id: str
    check_type: str
    object_name: str
    column: str | None
    severity: str
    expected: str
    actual: str | None
    status: str
    message: str = ""
    query: str | None = None


@dataclass
class ObjectRun:
    run_id: str
    object_name: str
    physical_name: str
    status: str
    rows_checked: int | None
    results: list[CheckResult]
    started_at: datetime
    finished_at: datetime
    error: str | None = None

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if r.status in (FAILED, ERROR)]

    @property
    def warned(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == WARNING]


@dataclass
class RunResult:
    contract_id: str
    contract_version: str
    batch_id: str | None
    status: str  # pass | warn | fail
    objects: list[ObjectRun] = field(default_factory=list)
    notifications: list[notify.Delivery] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status != "fail"

    def summary(self) -> str:
        lines = [f"Contract {self.contract_id} v{self.contract_version} batch={self.batch_id or '-'}: "
                 f"{self.status.upper()}"]
        for o in self.objects:
            rows = o.rows_checked if o.rows_checked is not None else "?"
            lines.append(f"  {o.object_name}: {o.status.upper()} ({rows} rows, {len(o.failed)} failed, "
                         f"{len(o.warned)} warnings)")
            for r in o.failed + o.warned:
                lines.append(f"    - [{r.status}] {r.check_id}: expected {r.expected or 'ok'}, got {r.actual}"
                             + (f" ({r.message})" if r.message else ""))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "batch_id": self.batch_id,
            "status": self.status,
            "objects": [
                {"run_id": o.run_id, "object": o.object_name, "status": o.status, "rows_checked": o.rows_checked,
                 "error": o.error, "checks": [r.__dict__ for r in o.results]}
                for o in self.objects
            ],
            "notifications": [
                {"channel": d.recipient.channel, "audience": d.recipient.audience,
                 "recipient": notify.mask(d.recipient.target), "status": d.status, "error": d.error}
                for d in self.notifications
            ],
        }


def _schema_checks(adapter: Adapter, obj: SchemaObject) -> tuple[list[CheckResult], set[str]]:
    """Compare the contract's columns with the live object. Returns results and the missing columns."""
    live = adapter.columns(obj.physical_name)
    results: list[CheckResult] = []
    if not live:
        results.append(CheckResult(f"{obj.name}.exists", "schema", obj.name, None, "error",
                                   "object exists", "missing", FAILED, f"{obj.physical_name} not found"))
        return results, {p.name.lower() for p in obj.properties}
    missing: set[str] = set()
    for prop in obj.properties:
        key = prop.name.lower()
        if key not in live:
            missing.add(key)
            results.append(CheckResult(f"{obj.name}.{prop.name}.exists", "schema", obj.name, prop.name,
                                       "error", "column exists", "missing", FAILED))
            continue
        match = type_matches(prop.logical_type, live[key])
        if match is not None:
            results.append(CheckResult(f"{obj.name}.{prop.name}.type", "schema", obj.name, prop.name, "error",
                                       f"logicalType {prop.logical_type}", live[key], PASSED if match else FAILED,
                                       "" if match else "physical type does not match the contract"))
    extra = sorted(set(live) - {p.name.lower() for p in obj.properties} - set(adapter.system_columns()))
    if extra and obj.properties:
        results.append(CheckResult(f"{obj.name}.no_extra_columns", "schema", obj.name, None, "warning",
                                   "no columns outside the contract", ", ".join(extra), WARNING,
                                   "new columns found; add them to the contract"))
    return results, missing


def _run_check(adapter: Adapter, check: Check, row_count: int | None) -> CheckResult:
    expected = describe_expectation(check.comparator, check.threshold, check.unit)
    try:
        value = adapter.evaluate(check)
        actual_num = float(0 if value is None else value)
        if check.unit == "percent":
            actual_num = (actual_num * 100.0 / row_count) if row_count else 0.0
        ok = compare(check.comparator, actual_num, check.threshold)
        actual = f"{actual_num:g}" + ("%" if check.unit == "percent" else "")
        status = PASSED if ok else (WARNING if check.severity == "warning" else FAILED)
        return CheckResult(check.check_id, check.check_type, check.object_name, check.column, check.severity,
                           expected, actual, status, check.description, check.sql)
    except UnsupportedCheck as exc:
        return CheckResult(check.check_id, check.check_type, check.object_name, check.column, check.severity,
                           expected, None, SKIPPED, str(exc), check.sql)
    except Exception as exc:  # noqa: BLE001 - a broken check is recorded, not raised
        adapter._rollback()
        return CheckResult(check.check_id, check.check_type, check.object_name, check.column, check.severity,
                           expected, None, ERROR, f"check could not run: {exc}", check.sql)


def _overall(statuses: list[str]) -> str:
    if any(s in (FAILED, ERROR, "fail") for s in statuses):
        return "fail"
    if any(s in (WARNING, "warn") for s in statuses):
        return "warn"
    return "pass"


def run_object(adapter: Adapter, obj: SchemaObject, where: str | None = None) -> ObjectRun:
    run_id = uuid.uuid4().hex
    started = utcnow()
    results, missing = _schema_checks(adapter, obj)
    table_missing = any(r.check_id == f"{obj.name}.exists" for r in results)
    row_count: int | None = None
    error: str | None = None
    if not table_missing:
        try:
            row_count = adapter.count(obj.physical_name, where)
        except Exception as exc:  # noqa: BLE001
            adapter._rollback()
            error = f"could not count rows: {exc}"
        for check in build_checks(obj, where):
            if check.column and check.column.lower() in missing:
                results.append(CheckResult(check.check_id, check.check_type, obj.name, check.column,
                                           check.severity, describe_expectation(check.comparator, check.threshold),
                                           None, SKIPPED, "column missing"))
                continue
            results.append(_run_check(adapter, check, row_count))
    statuses = [r.status for r in results] + ([ERROR] if error else [])
    return ObjectRun(run_id, obj.name, obj.physical_name, _overall(statuses), row_count, results, started,
                     utcnow(), error)


def _register_contract(meta: Adapter, schema: str, contract: Contract) -> None:
    key = {"contract_id": contract.id, "contract_version": contract.version, "yaml_hash": contract.yaml_hash}
    if not meta.meta_count(schema, "contracts", key):
        meta.meta_insert(schema, "contracts", [{
            **key, "name": contract.name, "domain": contract.domain, "owner": contract.owner,
            "source_path": contract.path, "loaded_at": utcnow()}])


def _log_object(meta: Adapter, schema: str, contract: Contract, run: ObjectRun, batch_id: str | None,
                pipeline: str | None, stage: str | None) -> None:
    meta.meta_insert(schema, "validation_runs", [{
        "run_id": run.run_id, "contract_id": contract.id, "contract_version": contract.version,
        "object_name": run.object_name, "batch_id": batch_id, "pipeline": pipeline, "stage": stage,
        "started_at": run.started_at, "finished_at": run.finished_at, "status": run.status,
        "checks_total": len(run.results), "checks_failed": len(run.failed), "checks_warned": len(run.warned),
        "rows_checked": run.rows_checked, "error_message": run.error,
    }])
    now = utcnow()
    meta.meta_insert(schema, "check_results", [
        {"run_id": run.run_id, "check_id": r.check_id, "check_type": r.check_type, "object_name": r.object_name,
         "column_name": r.column, "severity": r.severity, "expected": r.expected, "actual": r.actual,
         "status": r.status, "message": r.message, "query_text": r.query, "created_at": now}
        for r in run.results
    ])


def log_notifications(meta: Adapter, schema: str, run_id: str, run_kind: str,
                      deliveries: list[notify.Delivery], subject: str) -> None:
    now = utcnow()
    meta.meta_insert(schema, "notifications", [
        {"run_id": run_id, "run_kind": run_kind, "channel": d.recipient.channel,
         "recipient": notify.mask(d.recipient.target), "audience": d.recipient.audience, "status": d.status,
         "message": subject if d.status == "sent" else f"{subject} | error: {d.error}", "sent_at": now}
        for d in deliveries
    ])


def run_contract(contract: Contract, adapter: Adapter, config: Config | None = None, *,
                 batch_id: str | None = None, where: str | None = None, objects: list[str] | None = None,
                 pipeline: str | None = None, stage: str | None = None, stage_order: int | None = None,
                 send_notifications: bool = True, meta: Adapter | None = None) -> RunResult:
    """Validate a batch (or a whole table) against the contract and log everything in the meta tables.

    `where` limits the checks to one batch or micro-batch (SQL filter, or a JSON filter for MongoDB).
    `meta` is where results are stored; by default the same platform as the data.
    """
    config = config or Config()
    schema = config.meta_schema
    meta = meta or adapter
    adapter.connect()
    meta.connect()
    meta.meta_ensure(schema)
    _register_contract(meta, schema, contract)

    targets = [contract.object(o) for o in objects] if objects else contract.schema
    runs: list[ObjectRun] = []
    for obj in targets:
        run = run_object(adapter, obj, where)
        _log_object(meta, schema, contract, run, batch_id, pipeline, stage)
        if run.status == "fail" and config.on_fail == "quarantine":
            reasons = "; ".join(f"{r.check_id}={r.actual}" for r in run.failed)
            meta.meta_insert(schema, "quarantine_log", [{
                "run_id": run.run_id, "contract_id": contract.id, "object_name": run.object_name,
                "batch_id": batch_id, "reason": reasons, "created_at": utcnow(), "released_at": None}])
        if pipeline and stage:
            from .observe import record_event
            record_event(meta, schema, pipeline=pipeline, stage=stage, batch_id=batch_id,
                         object_name=run.physical_name, row_count=run.rows_checked, status=run.status,
                         stage_order=stage_order, details=f"contract {contract.id} v{contract.version}")
        runs.append(run)

    result = RunResult(contract.id, contract.version, batch_id, _overall([r.status for r in runs]), runs)

    if send_notifications and result.status in config.notify_on:
        recips = notify.recipients(contract.contacts, config.platform_team)
        if recips:
            subject = (f"[odcr] {result.status.upper()}: contract {contract.id} v{contract.version}"
                       + (f" batch {batch_id}" if batch_id else ""))
            result.notifications = notify.send(recips, subject, result.summary(), result.to_dict(),
                                               config.notifications)
            log_notifications(meta, schema, runs[0].run_id if runs else "-", "contract", result.notifications,
                              subject)
    return result
