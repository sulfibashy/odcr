"""Shared fixtures.

The `db` fixture runs every end-to-end test against every adapter that is reachable:

* always:          duckdb, sqlite, files (local folder), mongodb and kafka (in-memory when no server)
* with a server:   postgres, mysql, mariadb, sqlserver, oracle, trino, clickhouse, mongodb, kafka
                   (see docker-compose.yml)
* with credentials: snowflake, databricks, bigquery, redshift, athena, synapse, fabric, cosmosdb, db2, vertica,
                   teradata, saphana, hive, impala, eventhubs

Servers are found through environment variables (defaults match docker-compose.yml):
  ODCR_PG_HOST, ODCR_MYSQL_HOST, ODCR_MARIADB_HOST, ODCR_MSSQL_HOST, ODCR_ORACLE_HOST, ODCR_TRINO_HOST,
  ODCR_CLICKHOUSE_HOST, ODCR_MONGO_URI, ODCR_KAFKA_BOOTSTRAP. Any adapter can also be configured with ODCR_TEST_<ADAPTER>='{"key": "value", ...}' (JSON
  connection options, e.g. ODCR_TEST_SNOWFLAKE). Unreachable targets are skipped, never failed.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from odcr import samples
from odcr.adapters import get_adapter, resolve
from odcr.config import Config
from odcr.scaffold import contract_yaml

ALWAYS = ("duckdb", "sqlite", "files", "mongodb", "kafka")
SERVERS = ("postgres", "mysql", "mariadb", "sqlserver", "oracle", "trino", "clickhouse")
CLOUD = ("snowflake", "databricks", "bigquery", "redshift", "athena", "synapse", "fabric", "cosmosdb", "db2",
         "vertica", "teradata", "saphana", "hive", "impala", "eventhubs")
TARGETS = ALWAYS + SERVERS + CLOUD

_TMP = Path(os.environ.get("ODCR_TEST_TMP", "")) if os.environ.get("ODCR_TEST_TMP") else None


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def connection_options(target: str, tmp: Path | None = None) -> dict[str, Any] | None:
    """Connection options for a test target, or None when it is not configured."""
    override = os.environ.get(f"ODCR_TEST_{target.upper()}")
    if override:
        return json.loads(override)
    tmp = tmp or Path(os.environ.get("TMPDIR", "/tmp"))
    if target == "duckdb":
        return {"type": "duckdb", "path": str(tmp / "odcr_test.duckdb")}
    if target == "sqlite":
        return {"type": "sqlite", "path": str(tmp / "odcr_test.sqlite")}
    if target == "files":
        return {"type": "files", "meta_path": str(tmp / "odcr_files_meta.duckdb")}
    if target == "mongodb":
        uri = _env("ODCR_MONGO_URI")
        return {"type": "mongodb", "uri": uri, "database": "odcr_test"} if uri else \
            {"type": "mongodb", "mock": True, "database": "odcr_test"}
    if target == "kafka":
        servers = _env("ODCR_KAFKA_BOOTSTRAP")
        base = {"type": "kafka", "group_id": f"odcr_test_{uuid.uuid4().hex[:6]}", "timeout": 20,
                "meta_path": str(tmp / "odcr_kafka_meta.duckdb")}
        return {**base, "bootstrap_servers": servers} if servers else {**base, "mock": True}
    if target == "clickhouse" and _env("ODCR_CLICKHOUSE_HOST"):
        return {"type": "clickhouse", "host": _env("ODCR_CLICKHOUSE_HOST"), "port": _env("ODCR_CLICKHOUSE_PORT", "8123"),
                "user": _env("ODCR_CLICKHOUSE_USER", "odcr"), "password": _env("ODCR_CLICKHOUSE_PASSWORD", "odcr"),
                "database": _env("ODCR_CLICKHOUSE_DATABASE", "default")}
    if target == "postgres":
        return {"type": "postgres", "host": _env("ODCR_PG_HOST", "localhost"), "port": _env("ODCR_PG_PORT", "5432"),
                "user": _env("ODCR_PG_USER", "postgres"), "password": _env("ODCR_PG_PASSWORD", "postgres"),
                "database": _env("ODCR_PG_DATABASE", "odcr_test")}
    if target in ("mysql", "mariadb"):
        p = "MYSQL" if target == "mysql" else "MARIADB"
        if target == "mariadb" and not _env("ODCR_MARIADB_HOST"):
            return None
        return {"type": target, "host": _env(f"ODCR_{p}_HOST", "127.0.0.1"),
                "port": _env(f"ODCR_{p}_PORT", "3306" if target == "mysql" else "3307"),
                "user": _env(f"ODCR_{p}_USER", "odcr"), "password": _env(f"ODCR_{p}_PASSWORD", "odcr"),
                "database": _env(f"ODCR_{p}_DATABASE", "odcr_test")}
    if target == "sqlserver" and _env("ODCR_MSSQL_HOST"):
        return {"type": "sqlserver", "client": _env("ODCR_MSSQL_CLIENT", "pytds"), "host": _env("ODCR_MSSQL_HOST"),
                "port": _env("ODCR_MSSQL_PORT", "1433"), "user": _env("ODCR_MSSQL_USER", "sa"),
                "password": _env("ODCR_MSSQL_PASSWORD", "Odcr_Passw0rd!"), "database": _env("ODCR_MSSQL_DATABASE", "master"),
                "trust_server_certificate": True}
    if target == "oracle" and _env("ODCR_ORACLE_HOST"):
        return {"type": "oracle", "host": _env("ODCR_ORACLE_HOST"), "port": _env("ODCR_ORACLE_PORT", "1521"),
                "service_name": _env("ODCR_ORACLE_SERVICE", "FREEPDB1"), "user": _env("ODCR_ORACLE_USER", "odcr"),
                "password": _env("ODCR_ORACLE_PASSWORD", "odcr")}
    if target == "trino" and _env("ODCR_TRINO_HOST"):
        return {"type": "trino", "host": _env("ODCR_TRINO_HOST"), "port": _env("ODCR_TRINO_PORT", "8080"),
                "user": "odcr", "catalog": _env("ODCR_TRINO_CATALOG", "memory"),
                "schema": _env("ODCR_TRINO_SCHEMA", "default")}
    return None


_REACH: dict[str, str | None] = {}


def require(target: str, tmp: Path | None = None) -> dict[str, Any]:
    opts = connection_options(target, tmp)
    if opts is None:
        pytest.skip(f"{target}: not configured (see tests/conftest.py)")
    if target not in _REACH:
        try:
            a = get_adapter(opts)
            a.connect()
            a.ping()
            a.close()
            _REACH[target] = None
        except Exception as exc:  # noqa: BLE001
            _REACH[target] = f"{target} not reachable: {str(exc)[:200]}"
    if _REACH[target]:
        pytest.skip(_REACH[target])
    return opts


@pytest.fixture(scope="session")
def session_tmp(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("odcr")


@pytest.fixture(scope="session")
def meta_schema() -> str:
    return f"odcr_meta_{uuid.uuid4().hex[:6]}"


@pytest.fixture(params=TARGETS)
def db(request, session_tmp):
    """A connected adapter for each reachable target."""
    opts = require(request.param, session_tmp)
    adapter = get_adapter(opts)
    adapter.connect()
    adapter.test_target = request.param  # type: ignore[attr-defined]
    adapter.test_tmp = session_tmp  # type: ignore[attr-defined]
    yield adapter
    adapter.close()


def object_name(db, base: str | None = None) -> str:
    """A fresh table / collection / file path for one test."""
    base = base or f"orders_{uuid.uuid4().hex[:8]}"
    if db.dialect == "files":
        return str(Path(db.test_tmp) / "landing" / base / "part-0001.parquet")
    return base


def files_glob(db, name: str) -> str:
    return str(Path(name).parent / "*.parquet") if db.dialect == "files" else name


def where(db, batch: str) -> str:
    return resolve(db.dialect).where_example.replace("{batch_id}", batch)


def load(db, name: str, rows, columns=None) -> str:
    db.create_sample(name, columns or samples.COLUMNS, rows)
    return files_glob(db, name)


def drop(db, name: str) -> None:
    try:
        db.drop_table(name)
    except Exception:  # noqa: BLE001
        pass


class Webhook:
    """A local HTTP endpoint that records every JSON POST (stands in for Slack, Teams, PagerDuty, ...)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.calls.append({"path": self.path, "json": json.loads(body or b"{}"),
                                    "headers": dict(self.headers)})
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def webhook():
    w = Webhook()
    yield w
    w.close()


@pytest.fixture
def config(meta_schema: str, webhook: Webhook) -> Config:
    return Config(meta_schema=meta_schema, notifications={
        "notify_on": ["fail", "warn"], "platform_team": [{"type": "webhook", "url": f"{webhook.url}/platform"}]})


def contract_doc(db, physical: str, webhook_url: str | None = None, amount_null_severity: str = "warning") -> dict:
    doc = yaml.safe_load(contract_yaml(resolve(db.dialect)))
    doc["schema"][0]["physicalName"] = physical
    for p in doc["schema"][0]["properties"]:
        if p["name"] == "amount":
            p["quality"][0]["severity"] = amount_null_severity
    doc["support"] = [{"channel": "#source", "tool": "webhook", "url": f"{webhook_url}/source"}] if webhook_url else []
    return doc
