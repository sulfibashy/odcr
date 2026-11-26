"""MongoDB adapter (pymongo). Also works for Amazon DocumentDB and Azure Cosmos DB for MongoDB.

Objects are collections. Batch filters (`where`) are JSON filters, e.g. {"load_id": "42"}.
SQL quality rules are skipped; write MongoDB rules as ODCS custom rules:

    - type: custom
      engine: mongodb
      implementation: '{"amount": {"$lt": 0}}'   # counts matching documents
      mustBe: 0
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .base import UnsupportedCheck
from .document import DocumentAdapter, infer_columns, parse_filter

if TYPE_CHECKING:  # pragma: no cover
    from ..checks import Check


def _and(*filters: dict[str, Any]) -> dict[str, Any]:
    parts = [f for f in filters if f]
    if not parts:
        return {}
    return parts[0] if len(parts) == 1 else {"$and": parts}


class MongoDBAdapter(DocumentAdapter):
    dialect = "mongodb"
    driver = "pymongo"
    sample_size = 1000

    def _connect(self) -> Any:
        o = self.options
        if o.get("mock"):  # in-memory test double (mongomock); used by the test-suite when no server is running
            import mongomock

            client = mongomock.MongoClient()
        else:
            try:
                import pymongo
            except ImportError as exc:  # pragma: no cover
                raise ImportError("MongoDB support needs: pip install 'odcr[mongodb]'") from exc
            uri = o.get("uri") or f"mongodb://{o.get('host', 'localhost')}:{int(o.get('port', 27017))}"
            kwargs = {k: o[k] for k in ("username", "password", "authSource", "tls") if k in o}
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=int(o.get("timeout_ms", 5000)), **kwargs)
        return client

    @property
    def db(self) -> Any:
        self.connect()
        return self.conn[self.options.get("database", "odcr")]

    def _coll(self, name: str, database: str | None = None) -> Any:
        if "." in name and database is None:
            dbname, coll = name.split(".", 1)
            return self.conn[dbname][coll]
        return (self.conn[database] if database else self.db)[name]

    def ping(self) -> bool:
        self.connect()
        self.conn.admin.command("ping")
        return True

    def current_schema(self) -> str | None:
        return self.options.get("database", "odcr")

    def system_columns(self) -> tuple[str, ...]:
        return ("_id",)

    # ---------------------------------------------------------------- catalog and data
    def columns(self, name: str) -> dict[str, str]:
        coll = self._coll(name)
        docs = list(coll.find({}, limit=self.sample_size))
        if not docs and name.split(".")[-1] not in coll.database.list_collection_names():
            return {}
        return infer_columns(docs, self.system_columns()) or {"_id": "objectid"}

    def count(self, name: str, where: Any = None) -> int:
        return int(self._coll(name).count_documents(parse_filter(where)))

    def _metric(self, check: Check) -> tuple[Any, str]:
        base = parse_filter(check.where)
        coll = self._coll(check.physical_name)
        col, args, metric = check.column, check.args, check.metric
        if metric == "rowCount":
            f = base
        elif metric == "nullValues":
            f = _and(base, {col: None})
        elif metric == "missingValues":
            f = _and(base, {col: {"$in": [None] + [m for m in args.get("missingValues", []) if m is not None]}})
        elif metric == "invalidValues":
            f = _and(base, {col: {"$exists": True, "$ne": None, "$nin": list(args.get("validValues", []))}})
        elif metric == "duplicateValues":
            cols = [col] if col else list(args.get("properties", []))
            if not cols:
                raise ValueError("duplicateValues on an object needs arguments.properties")
            not_null = {c: {"$ne": None} for c in cols}
            pipeline = [
                {"$match": _and(base, not_null)},
                {"$group": {"_id": {c.replace(".", "_"): f"${c}" for c in cols}, "c": {"$sum": 1}}},
                {"$match": {"c": {"$gt": 1}}},
                {"$group": {"_id": None, "d": {"$sum": {"$subtract": ["$c", 1]}}}},
            ]
            rows = list(coll.aggregate(pipeline))
            return (rows[0]["d"] if rows else 0), json.dumps(pipeline, default=str)
        else:
            raise ValueError(f"Unsupported metric {metric}")
        return coll.count_documents(f), json.dumps(f, default=str)

    def evaluate(self, check: Check) -> Any:
        if check.metric:
            value, text = self._metric(check)
        elif check.check_type == "custom" and check.engine in ("mongodb", "mongo", "documentdb"):
            impl = check.query if isinstance(check.query, dict) else parse_filter(check.query)
            f = _and(parse_filter(check.where), impl)
            value, text = self._coll(check.physical_name).count_documents(f), json.dumps(f, default=str)
        else:
            raise UnsupportedCheck(f"{check.check_type} rules do not run on MongoDB; use a custom rule "
                                   "with engine: mongodb")
        check.sql = text
        return value

    def aggregate(self, name: str, where: Any, func: str, column: str | None) -> Any:
        base = parse_filter(where)
        coll = self._coll(name)
        if func == "rowCount":
            return coll.count_documents(base)
        if func == "nullCount":
            return coll.count_documents(_and(base, {column: None}))
        if func == "distinctCount":
            return len([v for v in coll.distinct(column, base) if v is not None])
        op = {"sum": "$sum", "min": "$min", "max": "$max"}[func]
        rows = list(coll.aggregate([{"$match": base}, {"$group": {"_id": None, "v": {op: f"${column}"}}}]))
        return rows[0]["v"] if rows else None

    def distinct_values(self, name: str, where: Any, column: str, limit: int) -> list[Any]:
        return self._coll(name).distinct(column, parse_filter(where))[:limit]

    # ---------------------------------------------------------------- meta (collections in the meta database)
    def meta_ensure(self, schema: str) -> None:
        self.connect()
        self._meta_ready.add(schema)

    def meta_insert(self, schema: str, table: str, rows: list[dict[str, Any]]) -> None:
        if rows:
            self._coll(table, database=schema).insert_many([{k: self.to_doc_value(v) for k, v in r.items()}
                                                            for r in rows])

    def meta_count(self, schema: str, table: str, where: dict[str, Any] | None = None) -> int:
        return int(self._coll(table, database=schema).count_documents(where or {}))

    def meta_select(self, schema: str, table: str, columns: list[str], where: dict[str, Any] | None = None,
                    order_by: str | None = None, descending: bool = True,
                    limit: int | None = None) -> list[dict[str, Any]]:
        cur = self._coll(table, database=schema).find(where or {})
        if order_by:
            cur = cur.sort(order_by, -1 if descending else 1)
        if limit:
            cur = cur.limit(int(limit))
        return [{c: doc.get(c) for c in columns} for doc in cur]

    # ---------------------------------------------------------------- sample data
    def drop_table(self, name: str) -> None:
        self._coll(name).drop()

    def create_sample(self, name: str, columns: list[tuple[str, str]], rows: list[Sequence[Any]]) -> None:
        self.drop_table(name)
        coll = self._coll(name)
        docs = [{c: self.to_doc_value(v) for (c, _), v in zip(columns, r)} for r in rows]
        if docs:
            coll.insert_many(docs)
        else:
            self.db.create_collection(name)
