"""Turn a contract's schema object into executable checks (portable SQL)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adapters.base import Adapter
from .contract import Property, QualityRule, SchemaObject


@dataclass
class Check:
    check_id: str
    check_type: str  # schema | quality | sql
    object_name: str
    column: str | None
    severity: str
    metric: str | None = None
    sql: str | None = None
    params: list[Any] = field(default_factory=list)
    comparator: str | None = None
    threshold: Any = None
    unit: str = "rows"
    description: str = ""


def relation(adapter: Adapter, physical_name: str, where: str | None = None) -> str:
    """The rows under test: the whole table, or one batch/micro-batch when `where` is given."""
    table = adapter.qualify(physical_name)
    if where:
        return f"(SELECT * FROM {table} WHERE {where}) src"
    return f"{table} src"


def compare(comparator: str | None, actual: Any, threshold: Any) -> bool:
    if comparator is None:
        return True
    a = float(actual)
    if comparator == "mustBe":
        return a == float(threshold)
    if comparator == "mustNotBe":
        return a != float(threshold)
    if comparator == "mustBeGreaterThan":
        return a > float(threshold)
    if comparator in ("mustBeGreaterOrEqualTo", "mustBeGreaterThanOrEqualTo"):
        return a >= float(threshold)
    if comparator == "mustBeLessThan":
        return a < float(threshold)
    if comparator in ("mustBeLessOrEqualTo", "mustBeLessThanOrEqualTo"):
        return a <= float(threshold)
    if comparator == "mustBeBetween":
        lo, hi = threshold
        return float(lo) <= a <= float(hi)
    if comparator == "mustNotBeBetween":
        lo, hi = threshold
        return not (float(lo) <= a <= float(hi))
    raise ValueError(f"Unknown comparator {comparator}")


def describe_expectation(comparator: str | None, threshold: Any, unit: str = "rows") -> str:
    if comparator is None:
        return ""
    words = {
        "mustBe": "=", "mustNotBe": "!=", "mustBeGreaterThan": ">", "mustBeGreaterOrEqualTo": ">=",
        "mustBeGreaterThanOrEqualTo": ">=", "mustBeLessThan": "<", "mustBeLessOrEqualTo": "<=",
        "mustBeLessThanOrEqualTo": "<=",
    }
    suffix = "%" if unit == "percent" else ""
    if comparator in ("mustBeBetween", "mustNotBeBetween"):
        neg = "not " if comparator.startswith("mustNot") else ""
        return f"{neg}between {threshold[0]}{suffix} and {threshold[1]}{suffix}"
    return f"{words[comparator]} {threshold}{suffix}"


def _metric_sql(adapter: Adapter, metric: str, rel: str, column: str | None,
                args: dict[str, Any]) -> tuple[str, list[Any]]:
    q = adapter.quote
    if metric == "rowCount":
        return f"SELECT COUNT(*) FROM {rel}", []
    if metric == "nullValues":
        return f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NULL", []  # type: ignore[arg-type]
    if metric == "missingValues":
        missing = [m for m in args.get("missingValues", []) if m is not None]
        if missing:
            return (f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NULL OR {q(column)} IN "  # type: ignore
                    f"({adapter.params(len(missing))})", missing)
        return f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NULL", []  # type: ignore[arg-type]
    if metric == "duplicateValues":
        cols = [column] if column else list(args.get("properties", []))
        if not cols:
            raise ValueError("duplicateValues on an object needs arguments.properties")
        group = ", ".join(q(c) for c in cols)
        not_null = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
        return (f"SELECT COALESCE(SUM(c - 1), 0) FROM (SELECT COUNT(*) AS c FROM {rel} WHERE {not_null} "
                f"GROUP BY {group} HAVING COUNT(*) > 1) d", [])
    if metric == "invalidValues":
        valid = list(args.get("validValues", []))
        return (f"SELECT COUNT(*) FROM {rel} WHERE {q(column)} IS NOT NULL AND {q(column)} NOT IN "  # type: ignore
                f"({adapter.params(len(valid))})", valid)
    raise ValueError(f"Unsupported metric {metric}")


def _render_sql(query: str, rel: str, adapter: Adapter, column: str | None) -> str:
    out = query
    for token in ("${object}", "{object}", "${table}", "{table}"):
        out = out.replace(token, rel)
    if column:
        for token in ("${property}", "{property}", "${column}", "{column}"):
            out = out.replace(token, adapter.quote(column))
    return out


def _quality_checks(adapter: Adapter, obj: SchemaObject, rel: str, rules: list[QualityRule],
                    prop: Property | None) -> list[Check]:
    checks: list[Check] = []
    col = prop.name if prop else None
    base = f"{obj.name}.{col}" if col else obj.name
    for i, rule in enumerate(rules):
        if rule.type not in ("library", "sql"):
            continue
        if rule.type == "library":
            sql, params = _metric_sql(adapter, rule.metric or "", rel, col, rule.arguments)
            cid = rule.name or f"{base}.{rule.metric}"
            ctype = "quality"
        else:
            sql, params = _render_sql(rule.query or "", rel, adapter, col), []
            cid = rule.name or f"{base}.sql_{i + 1}"
            ctype = "sql"
        checks.append(Check(
            check_id=cid, check_type=ctype, object_name=obj.name, column=col, severity=rule.severity,
            metric=rule.metric, sql=sql, params=params, comparator=rule.comparator,
            threshold=rule.threshold, unit=rule.unit, description=rule.description or "",
        ))
    return checks


def build_checks(adapter: Adapter, obj: SchemaObject, where: str | None = None) -> list[Check]:
    """Data checks for one schema object (schema checks are run separately against live metadata)."""
    rel = relation(adapter, obj.physical_name, where)
    checks: list[Check] = []
    for prop in obj.properties:
        if prop.required or prop.primary_key:
            checks.append(Check(
                check_id=f"{obj.name}.{prop.name}.required", check_type="quality", object_name=obj.name,
                column=prop.name, severity="error", metric="nullValues",
                sql=_metric_sql(adapter, "nullValues", rel, prop.name, {})[0],
                comparator="mustBe", threshold=0, description="required: no NULL values",
            ))
        if prop.unique or prop.primary_key:
            checks.append(Check(
                check_id=f"{obj.name}.{prop.name}.unique", check_type="quality", object_name=obj.name,
                column=prop.name, severity="error", metric="duplicateValues",
                sql=_metric_sql(adapter, "duplicateValues", rel, prop.name, {})[0],
                comparator="mustBe", threshold=0, description="unique: no duplicate values",
            ))
        checks.extend(_quality_checks(adapter, obj, rel, prop.quality, prop))
    checks.extend(_quality_checks(adapter, obj, rel, obj.quality, None))
    return checks
