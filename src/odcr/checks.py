"""Turn a contract's schema object into checks. Adapters decide how each check runs on their platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contract import Property, QualityRule, SchemaObject


@dataclass
class Check:
    check_id: str
    check_type: str  # quality | sql | custom
    object_name: str
    physical_name: str
    column: str | None
    severity: str
    where: str | None = None
    metric: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    query: str | None = None  # sql rules and custom rules (implementation)
    engine: str | None = None  # custom rules: sql, mongodb, cosmosdb, ...
    comparator: str | None = None
    threshold: Any = None
    unit: str = "rows"
    description: str = ""
    sql: str | None = None  # the query that actually ran (set by the adapter)
    params: list[Any] = field(default_factory=list)


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


def _rule_checks(obj: SchemaObject, rules: list[QualityRule], prop: Property | None,
                 where: str | None) -> list[Check]:
    checks: list[Check] = []
    col = prop.name if prop else None
    base = f"{obj.name}.{col}" if col else obj.name
    for i, rule in enumerate(rules):
        if rule.type == "library":
            cid, ctype = rule.name or f"{base}.{rule.metric}", "quality"
        elif rule.type == "sql":
            cid, ctype = rule.name or f"{base}.sql_{i + 1}", "sql"
        elif rule.type == "custom" and rule.engine and rule.implementation is not None:
            cid, ctype = rule.name or f"{base}.custom_{i + 1}", "custom"
        else:
            continue  # text rules and custom rules without an engine are documentation only
        checks.append(Check(
            check_id=cid, check_type=ctype, object_name=obj.name, physical_name=obj.physical_name, column=col,
            severity=rule.severity, where=where, metric=rule.metric if rule.type == "library" else None,
            args=rule.arguments, query=rule.query if rule.type == "sql" else rule.implementation,
            engine=rule.engine if rule.type == "custom" else None, comparator=rule.comparator,
            threshold=rule.threshold, unit=rule.unit, description=rule.description or "",
        ))
    return checks


def build_checks(obj: SchemaObject, where: str | None = None) -> list[Check]:
    """Data checks for one schema object. Schema checks run separately against the live catalog."""
    checks: list[Check] = []
    for prop in obj.properties:
        common = dict(object_name=obj.name, physical_name=obj.physical_name, column=prop.name, severity="error",
                      where=where, comparator="mustBe", threshold=0)
        if prop.required or prop.primary_key:
            checks.append(Check(check_id=f"{obj.name}.{prop.name}.required", check_type="quality",
                                metric="nullValues", description="required: no NULL values", **common))
        if prop.unique or prop.primary_key:
            checks.append(Check(check_id=f"{obj.name}.{prop.name}.unique", check_type="quality",
                                metric="duplicateValues", description="unique: no duplicate values", **common))
        checks.extend(_rule_checks(obj, prop.quality, prop, where))
    checks.extend(_rule_checks(obj, obj.quality, None, where))
    return checks
