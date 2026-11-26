"""Shared helpers for document databases (MongoDB, Azure Cosmos DB)."""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from .base import Adapter

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}.*)?$")


def infer_type(value: Any, iso_dates: bool = False) -> str:
    """Map a document value to a type name understood by `type_matches`."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, (float, Decimal)):
        return "double"
    if isinstance(value, (dt.datetime, dt.date)):
        return "bsondate"
    if isinstance(value, str):
        return "bsondate" if iso_dates and _ISO_DATE.match(value) else "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    name = type(value).__name__.lower()
    return {"decimal128": "decimal128", "objectid": "objectid"}.get(name, name)


def infer_columns(docs: Iterable[dict[str, Any]], system: tuple[str, ...] = (),
                  iso_dates: bool = False) -> dict[str, str]:
    """Top-level field -> most common non-null type across sampled documents."""
    seen: dict[str, dict[str, int]] = {}
    for doc in docs:
        for key, value in doc.items():
            if key in system:
                continue
            counts = seen.setdefault(key.lower(), {})
            if value is not None:
                t = infer_type(value, iso_dates)
                counts[t] = counts.get(t, 0) + 1
    return {k: (max(v, key=v.get) if v else "") for k, v in seen.items()}


def parse_filter(where: Any) -> dict[str, Any]:
    if where is None or where == "":
        return {}
    if isinstance(where, dict):
        return where
    try:
        value = json.loads(where)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Document filters are JSON, e.g. {{"load_id": "42"}}; got: {where}') from exc
    if not isinstance(value, dict):
        raise ValueError("Document filter must be a JSON object")
    return value


class DocumentAdapter(Adapter):
    """Base for document databases: objects are collections/containers; `where` is a JSON filter."""

    kind = "document"
    paramstyle = "inline"

    def qualify(self, name: str) -> str:
        return name

    def quote(self, identifier: str) -> str:
        return identifier

    def relation(self, name: str, where: str | None = None) -> str:
        return f"{name} {where or ''}".strip()

    def limit(self, select_sql: str, n: int) -> str:  # pragma: no cover - not used for documents
        return select_sql

    def to_doc_value(self, value: Any) -> Any:
        if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
            return dt.datetime(value.year, value.month, value.day)
        if isinstance(value, Decimal):
            return float(value)
        return value
