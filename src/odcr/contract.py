"""Load and validate ODCS (Open Data Contract Standard) v3 contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_KINDS = {"DataContract"}

# ODCS 3.1+ library metrics, plus the older ODCS 3.0 rule names as aliases.
LIBRARY_METRICS = {
    "rowCount": "rowCount",
    "nullValues": "nullValues",
    "nullCheck": "nullValues",
    "missingValues": "missingValues",
    "duplicateValues": "duplicateValues",
    "duplicateCount": "duplicateValues",
    "invalidValues": "invalidValues",
    "validValues": "invalidValues",
}

COMPARATORS = (
    "mustBe",
    "mustNotBe",
    "mustBeGreaterThan",
    "mustBeGreaterOrEqualTo",
    "mustBeGreaterThanOrEqualTo",
    "mustBeLessThan",
    "mustBeLessOrEqualTo",
    "mustBeLessThanOrEqualTo",
    "mustBeBetween",
    "mustNotBeBetween",
)


class ContractError(ValueError):
    """Raised when a contract file is missing or invalid."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


@dataclass
class QualityRule:
    type: str  # library | sql | text | custom
    metric: str | None = None
    query: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    comparator: str | None = None
    threshold: Any = None
    unit: str = "rows"
    severity: str = "error"
    name: str | None = None
    description: str | None = None
    engine: str | None = None  # custom rules
    implementation: Any = None  # custom rules


@dataclass
class Property:
    name: str
    logical_type: str | None = None
    physical_type: str | None = None
    required: bool = False
    unique: bool = False
    primary_key: bool = False
    quality: list[QualityRule] = field(default_factory=list)


@dataclass
class SchemaObject:
    name: str
    physical_name: str
    properties: list[Property] = field(default_factory=list)
    quality: list[QualityRule] = field(default_factory=list)


@dataclass
class Contact:
    kind: str  # slack | teams | email | webhook | other
    target: str
    name: str | None = None


@dataclass
class Contract:
    id: str
    version: str
    name: str | None
    domain: str | None
    status: str | None
    owner: str | None
    schema: list[SchemaObject]
    contacts: list[Contact]
    raw: dict[str, Any]
    yaml_hash: str
    path: str | None = None

    def object(self, name: str) -> SchemaObject:
        for obj in self.schema:
            if obj.name == name or obj.physical_name == name:
                return obj
        raise KeyError(f"Schema object '{name}' not found in contract {self.id}")


def _severity(item: dict[str, Any]) -> str:
    value = str(item.get("severity", "error")).lower()
    if value in ("warn", "warning", "minor", "low", "info"):
        return "warning"
    return "error"


def _parse_quality(items: Any, where: str, problems: list[str]) -> list[QualityRule]:
    rules: list[QualityRule] = []
    if items is None:
        return rules
    if not isinstance(items, list):
        problems.append(f"{where}.quality must be a list")
        return rules
    for i, item in enumerate(items):
        loc = f"{where}.quality[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{loc} must be a mapping")
            continue
        rtype = str(item.get("type", "library"))
        comparator = next((c for c in COMPARATORS if c in item), None)
        threshold = item.get(comparator) if comparator else None
        metric = item.get("metric") or item.get("rule")
        rule = QualityRule(
            type=rtype,
            metric=LIBRARY_METRICS.get(metric, metric) if metric else None,
            query=item.get("query"),
            arguments=dict(item.get("arguments") or {}),
            comparator=comparator,
            threshold=threshold,
            unit=str(item.get("unit", "rows")),
            severity=_severity(item),
            name=item.get("name"),
            description=item.get("description"),
            engine=(str(item["engine"]).lower() if item.get("engine") else None),
            implementation=item.get("implementation"),
        )
        # ODCS 3.0 style: validValues given directly on the rule
        if "validValues" in item and "validValues" not in rule.arguments:
            rule.arguments["validValues"] = item["validValues"]
        if rtype == "library":
            if not rule.metric:
                problems.append(f"{loc}: library rule needs 'metric'")
            elif rule.metric not in LIBRARY_METRICS.values():
                problems.append(f"{loc}: unsupported metric '{metric}'")
            if rule.metric == "invalidValues" and not rule.arguments.get("validValues"):
                problems.append(f"{loc}: invalidValues needs arguments.validValues")
        elif rtype == "sql":
            if not rule.query:
                problems.append(f"{loc}: sql rule needs 'query'")
        elif rtype == "text":
            pass  # documented only, not executed
        elif rtype == "custom":
            if rule.engine and rule.implementation is None:
                problems.append(f"{loc}: custom rule with an engine needs 'implementation'")
        else:
            problems.append(f"{loc}: unknown quality type '{rtype}'")
        executable = rtype in ("library", "sql") or (rtype == "custom" and rule.engine)
        if executable and comparator is None:
            # ODCS default expectation for counts of bad rows is zero
            if rule.metric != "rowCount":
                rule.comparator, rule.threshold = "mustBe", 0
            else:
                problems.append(f"{loc}: rowCount needs a comparator such as mustBeGreaterThan")
        if comparator in ("mustBeBetween", "mustNotBeBetween"):
            if not (isinstance(threshold, list) and len(threshold) == 2):
                problems.append(f"{loc}: {comparator} needs a list of two numbers")
        rules.append(rule)
    return rules


def _contacts(doc: dict[str, Any]) -> list[Contact]:
    from .config import interpolate  # webhook URLs can come from env vars, keeping secrets out of Git
    from .notify import CHANNELS, channel_name

    contacts: list[Contact] = []
    for ch in interpolate(doc.get("support") or []):
        if not isinstance(ch, dict):
            continue
        tool = channel_name(ch.get("tool", ""))
        url = str(ch.get("url") or "")
        if tool == "email" or url.startswith("mailto:"):
            target = (url or str(ch.get("channel", ""))).replace("mailto:", "")
            if target:
                contacts.append(Contact("email", target, ch.get("channel")))
        elif tool in CHANNELS and tool != "console" and url:
            contacts.append(Contact(tool, url, ch.get("channel")))
    return contacts


def _owner(doc: dict[str, Any]) -> str | None:
    team = doc.get("team")
    members = team.get("members") if isinstance(team, dict) else team
    for m in members or []:
        if isinstance(m, dict) and str(m.get("role", "")).lower() == "owner":
            return m.get("username") or m.get("name")
    return None


def parse_contract(doc: Any, path: str | None = None, text: str | None = None) -> Contract:
    problems: list[str] = []
    if not isinstance(doc, dict):
        raise ContractError("Contract must be a YAML mapping", ["root is not a mapping"])
    for key in ("apiVersion", "kind", "id", "version", "schema"):
        if key not in doc:
            problems.append(f"missing required field '{key}'")
    kind = doc.get("kind")
    if kind is not None and kind not in SUPPORTED_KINDS:
        problems.append(f"kind must be DataContract, got '{kind}'")
    api = str(doc.get("apiVersion", ""))
    if api and not api.lstrip("v").startswith("3"):
        problems.append(f"apiVersion '{api}' is not ODCS v3")

    objects: list[SchemaObject] = []
    schema = doc.get("schema") or []
    if not isinstance(schema, list):
        problems.append("schema must be a list of objects")
        schema = []
    for i, obj in enumerate(schema):
        where = f"schema[{i}]"
        if not isinstance(obj, dict) or not obj.get("name"):
            problems.append(f"{where} needs a name")
            continue
        props: list[Property] = []
        for j, p in enumerate(obj.get("properties") or []):
            pw = f"{where}.properties[{j}]"
            if not isinstance(p, dict) or not p.get("name"):
                problems.append(f"{pw} needs a name")
                continue
            props.append(
                Property(
                    name=str(p["name"]),
                    logical_type=p.get("logicalType"),
                    physical_type=p.get("physicalType"),
                    required=bool(p.get("required", False)),
                    unique=bool(p.get("unique", False)),
                    primary_key=bool(p.get("primaryKey", False)),
                    quality=_parse_quality(p.get("quality"), pw, problems),
                )
            )
        objects.append(
            SchemaObject(
                name=str(obj["name"]),
                physical_name=str(obj.get("physicalName") or obj["name"]),
                properties=props,
                quality=_parse_quality(obj.get("quality"), where, problems),
            )
        )
    if problems:
        raise ContractError(f"Invalid contract {path or ''}".strip(), problems)

    raw_text = text if text is not None else yaml.safe_dump(doc, sort_keys=True)
    return Contract(
        id=str(doc["id"]),
        version=str(doc["version"]),
        name=doc.get("name"),
        domain=doc.get("domain"),
        status=doc.get("status"),
        owner=_owner(doc),
        schema=objects,
        contacts=_contacts(doc),
        raw=doc,
        yaml_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        path=path,
    )


def load_contract(path: str | Path) -> Contract:
    p = Path(path)
    if not p.exists():
        raise ContractError(f"Contract file not found: {p}")
    text = p.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ContractError(f"Contract is not valid YAML: {exc}") from exc
    return parse_contract(doc, path=str(p), text=text)
