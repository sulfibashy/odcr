"""Reconciliation: compare a source and a target for the same batch, even across different platforms.

Example spec (reconciliation.yaml):

    kind: Reconciliation
    id: orders-pg-to-mysql
    source: {connection: source-pg, object: public.orders, where: "load_id = '{batch_id}'"}
    target: {connection: dwh-mysql, object: orders, where: "load_id = '{batch_id}'"}
    checks:
      - type: rowCount
      - type: sum
        column: amount
        tolerance: 0.01
      - type: missingKeys
        column: order_id
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import notify
from .adapters.base import Adapter
from .checks import relation
from .config import Config
from .contract import Contact, ContractError
from .meta import ensure_meta, table_name

AGGREGATES = {"rowCount", "sum", "min", "max", "distinctCount", "nullCount"}
CHECK_TYPES = AGGREGATES | {"missingKeys"}


@dataclass
class Side:
    connection: str | None
    object: str
    where: str | None = None


@dataclass
class ReconCheck:
    type: str
    source_column: str | None = None
    target_column: str | None = None
    tolerance: float = 0.0
    tolerance_percent: float | None = None
    max_keys: int = 1_000_000
    name: str | None = None

    @property
    def check_id(self) -> str:
        return self.name or (f"{self.type}({self.source_column})" if self.source_column else self.type)


@dataclass
class Reconciliation:
    id: str
    source: Side
    target: Side
    checks: list[ReconCheck]
    contract: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconCheckResult:
    check_id: str
    check_type: str
    column: str | None
    source_value: str | None
    target_value: str | None
    difference: str | None
    tolerance: str
    status: str
    message: str = ""


@dataclass
class ReconResult:
    run_id: str
    recon_id: str
    batch_id: str | None
    status: str
    results: list[ReconCheckResult]
    notifications: list[notify.Delivery] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def summary(self) -> str:
        lines = [f"Reconciliation {self.recon_id} batch={self.batch_id or '-'}: {self.status.upper()}"]
        for r in self.results:
            mark = "ok" if r.status == "passed" else r.status
            lines.append(f"  - [{mark}] {r.check_id}: source={r.source_value} target={r.target_value}"
                         + (f" diff={r.difference}" if r.difference not in (None, "0") else "")
                         + (f" ({r.message})" if r.message else ""))
        return "\n".join(lines)


def _side(doc: Any, name: str, problems: list[str]) -> Side:
    if not isinstance(doc, dict) or not doc.get("object"):
        problems.append(f"{name} needs an 'object'")
        return Side(None, "")
    return Side(doc.get("connection"), str(doc["object"]), doc.get("where"))


def parse_reconciliation(doc: Any) -> Reconciliation:
    problems: list[str] = []
    if not isinstance(doc, dict):
        raise ContractError("Reconciliation must be a YAML mapping")
    if doc.get("kind", "Reconciliation") != "Reconciliation":
        problems.append("kind must be Reconciliation")
    if not doc.get("id"):
        problems.append("missing 'id'")
    checks: list[ReconCheck] = []
    for i, c in enumerate(doc.get("checks") or [{"type": "rowCount"}]):
        ctype = str(c.get("type", "")) if isinstance(c, dict) else ""
        if ctype not in CHECK_TYPES:
            problems.append(f"checks[{i}]: unknown type '{ctype}' (use {', '.join(sorted(CHECK_TYPES))})")
            continue
        col = c.get("column")
        src, tgt = c.get("sourceColumn", col), c.get("targetColumn", col)
        if ctype != "rowCount" and not (src and tgt):
            problems.append(f"checks[{i}]: {ctype} needs 'column' (or sourceColumn and targetColumn)")
        checks.append(ReconCheck(ctype, src, tgt, float(c.get("tolerance", 0)),
                                 None if c.get("tolerancePercent") is None else float(c["tolerancePercent"]),
                                 int(c.get("maxKeys", 1_000_000)), c.get("name")))
    source = _side(doc.get("source"), "source", problems)
    target = _side(doc.get("target"), "target", problems)
    if problems:
        raise ContractError("Invalid reconciliation", problems)
    return Reconciliation(str(doc["id"]), source, target, checks, doc.get("contract"), doc)


def load_reconciliation(path: str | Path) -> Reconciliation:
    p = Path(path)
    if not p.exists():
        raise ContractError(f"Reconciliation file not found: {p}")
    return parse_reconciliation(yaml.safe_load(p.read_text(encoding="utf-8")))


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v: Any) -> str | None:
    if v is None:
        return None
    f = _num(v)
    return f"{f:g}" if f is not None and not isinstance(v, str) else str(v)


def _aggregate(adapter: Adapter, side: Side, check: ReconCheck, column: str | None, batch_id: str | None) -> Any:
    where = side.where.replace("{batch_id}", str(batch_id)) if side.where and batch_id is not None else side.where
    rel = relation(adapter, side.object, where)
    q = adapter.quote
    expr = {
        "rowCount": "COUNT(*)",
        "sum": f"SUM({q(column)})" if column else "",
        "min": f"MIN({q(column)})" if column else "",
        "max": f"MAX({q(column)})" if column else "",
        "distinctCount": f"COUNT(DISTINCT {q(column)})" if column else "",
        "nullCount": f"SUM(CASE WHEN {q(column)} IS NULL THEN 1 ELSE 0 END)" if column else "",
    }[check.type]
    return adapter.scalar(f"SELECT {expr} FROM {rel}")


def _keys(adapter: Adapter, side: Side, column: str, batch_id: str | None, limit: int) -> set[str]:
    where = side.where.replace("{batch_id}", str(batch_id)) if side.where and batch_id is not None else side.where
    rel = relation(adapter, side.object, where)
    sql = adapter.limit(f"SELECT DISTINCT {adapter.quote(column)} FROM {rel}", limit + 1)
    keys = {str(r[0]) for r in adapter.fetchall(sql) if r[0] is not None}
    if len(keys) > limit:
        raise ValueError(f"more than maxKeys={limit} keys; narrow the batch with 'where'")
    return keys


def _compare(check: ReconCheck, s: Any, t: Any) -> ReconCheckResult:
    sn, tn = _num(s), _num(t)
    tol_text = f"{check.tolerance:g}" + (f" or {check.tolerance_percent:g}%" if check.tolerance_percent else "")
    if sn is None or tn is None:
        same = s == t
        return ReconCheckResult(check.check_id, check.type, check.source_column, _fmt(s), _fmt(t), None, tol_text,
                                "passed" if same else "failed", "" if same else "values differ")
    diff = tn - sn
    allowed = check.tolerance
    if check.tolerance_percent is not None and sn:
        allowed = max(allowed, abs(sn) * check.tolerance_percent / 100.0)
    ok = math.isclose(diff, 0.0, abs_tol=1e-9) or abs(diff) <= allowed + 1e-9
    return ReconCheckResult(check.check_id, check.type, check.source_column, _fmt(s), _fmt(t), f"{diff:g}",
                            tol_text, "passed" if ok else "failed", "" if ok else "outside tolerance")


def run_reconciliation(recon: Reconciliation, source: Adapter, target: Adapter, config: Config | None = None, *,
                       batch_id: str | None = None, meta: Adapter | None = None, pipeline: str | None = None,
                       contacts: list[Contact] | None = None, send_notifications: bool = True) -> ReconResult:
    """Compare source and target. Results are logged in the meta tables of `meta` (default: the target)."""
    config = config or Config()
    meta = meta or target
    run_id = uuid.uuid4().hex
    from .runner import utcnow
    started = utcnow()
    results: list[ReconCheckResult] = []
    error: str | None = None
    try:
        source.connect()
        target.connect()
        for check in recon.checks:
            try:
                if check.type == "missingKeys":
                    sk = _keys(source, recon.source, check.source_column or "", batch_id, check.max_keys)
                    tk = _keys(target, recon.target, check.target_column or "", batch_id, check.max_keys)
                    missing, extra = sorted(sk - tk), sorted(tk - sk)
                    ok = not missing and not extra
                    msg = ""
                    if missing:
                        msg += f"{len(missing)} missing in target (e.g. {', '.join(missing[:5])})"
                    if extra:
                        msg += ("; " if msg else "") + f"{len(extra)} only in target (e.g. {', '.join(extra[:5])})"
                    results.append(ReconCheckResult(check.check_id, check.type, check.source_column, str(len(sk)),
                                                    str(len(tk)), str(len(missing) + len(extra)), "0",
                                                    "passed" if ok else "failed", msg))
                else:
                    s = _aggregate(source, recon.source, check, check.source_column, batch_id)
                    t = _aggregate(target, recon.target, check, check.target_column, batch_id)
                    results.append(_compare(check, s, t))
            except Exception as exc:  # noqa: BLE001
                results.append(ReconCheckResult(check.check_id, check.type, check.source_column, None, None, None,
                                                "", "error", f"check could not run: {exc}"))
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    status = "fail" if error or any(r.status != "passed" for r in results) else "pass"
    result = ReconResult(run_id, recon.id, batch_id, status, results)

    meta.connect()
    schema = config.meta_schema
    ensure_meta(meta, schema)
    meta.insert(table_name(meta, schema, "reconciliation_runs"), {
        "run_id": run_id, "recon_id": recon.id, "source_object": recon.source.object,
        "target_object": recon.target.object, "batch_id": batch_id, "pipeline": pipeline, "started_at": started,
        "finished_at": utcnow(), "status": status, "checks_total": len(results),
        "checks_failed": sum(1 for r in results if r.status != "passed"), "error_message": error,
    })
    now = utcnow()
    meta.insert_many(table_name(meta, schema, "reconciliation_results"), [
        {"run_id": run_id, "check_id": r.check_id, "check_type": r.check_type, "column_name": r.column,
         "source_value": r.source_value, "target_value": r.target_value, "difference": r.difference,
         "tolerance": r.tolerance, "status": r.status, "message": r.message, "created_at": now}
        for r in results
    ])
    if send_notifications and status in config.notify_on:
        recips = notify.recipients(contacts or [], config.platform_team)
        if recips:
            subject = f"[odcr] {status.upper()}: reconciliation {recon.id}" + (f" batch {batch_id}" if batch_id else "")
            result.notifications = notify.send(recips, subject, result.summary(), {"recon_id": recon.id},
                                               config.notifications.get("smtp"))
            from .runner import log_notifications
            log_notifications(meta, schema, run_id, "reconciliation", result.notifications, subject)
    return result
