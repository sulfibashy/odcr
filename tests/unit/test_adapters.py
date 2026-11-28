"""Adapter behaviour that needs no database: SQL generation, quoting, binding, catalogs, meta DDL."""

import datetime as dt
from decimal import Decimal

import pytest

from odcr.adapters import ADAPTERS, adapter_class, get_adapter, resolve, type_matches
from odcr.adapters.base import Adapter, UnsupportedCheck
from odcr.adapters.cosmosdb import CosmosDBAdapter, is_null, prop, where_clause
from odcr.adapters.document import infer_columns, parse_filter
from odcr.checks import Check, build_checks, compare, describe_expectation
from odcr.contract import parse_contract
from odcr.meta import TABLES, ddl


def make(name, **kw):
    return adapter_class(name)(**kw)


def test_every_adapter_is_registered_and_importable():
    assert len(ADAPTERS) >= 18
    for name, info in ADAPTERS.items():
        a = make(name)
        assert isinstance(a, Adapter)
        assert info.connection["type"] == name
        assert a.driver_version()


@pytest.mark.parametrize("alias,name", [("postgresql", "postgres"), ("MariaDB", "mysql"), ("mssql", "sqlserver"),
                                        ("azure-sql", "sqlserver"), ("azure-databricks", "databricks"),
                                        ("aws-databricks", "databricks"), ("gcp-databricks", "databricks"),
                                        ("starburst", "trino"), ("documentdb", "mongodb"), ("adls", "files"),
                                        ("s3", "files"), ("cosmos", "cosmosdb"), ("aurora-postgres", "postgres")])
def test_aliases(alias, name):
    assert resolve(alias).name == name


def test_unknown_adapter():
    with pytest.raises(ValueError, match="odcr adapters"):
        get_adapter({"type": "excel"})


@pytest.mark.parametrize("comp,actual,thr,ok", [
    ("mustBe", 0, 0, True), ("mustBe", 1, 0, False), ("mustNotBe", 1, 0, True),
    ("mustBeGreaterThan", 5, 4, True), ("mustBeGreaterThan", 4, 4, False),
    ("mustBeGreaterOrEqualTo", 4, 4, True), ("mustBeGreaterThanOrEqualTo", 3, 4, False),
    ("mustBeLessThan", 3, 4, True), ("mustBeLessOrEqualTo", 4, 4, True), ("mustBeLessThanOrEqualTo", 5, 4, False),
    ("mustBeBetween", 5, [1, 10], True), ("mustBeBetween", 11, [1, 10], False),
    ("mustNotBeBetween", 11, [1, 10], True), ("mustNotBeBetween", 5, [1, 10], False), (None, 1, None, True),
])
def test_compare(comp, actual, thr, ok):
    assert compare(comp, actual, thr) is ok


def test_compare_and_describe_edges():
    with pytest.raises(ValueError):
        compare("mustBeAwesome", 1, 1)
    assert describe_expectation("mustBeLessOrEqualTo", 1, "percent") == "<= 1%"
    assert describe_expectation("mustNotBeBetween", [1, 2]) == "not between 1 and 2"


@pytest.mark.parametrize("logical,physical,ok", [
    ("integer", "integer", True), ("integer", "bigint", True), ("integer", "number", True), ("integer", "int64", True),
    ("integer", "varchar", False), ("number", "decimal(12,2)", True), ("number", "numeric", True),
    ("number", "float64", True), ("number", "binary_double", True), ("string", "character varying", True),
    ("string", "varchar2", True), ("string", "nvarchar", True), ("string", "string", True), ("string", "int", False),
    ("date", "date", True), ("date", "datetime", False), ("date", "bsondate", True),
    ("timestamp", "timestamp_ntz", True), ("timestamp", "datetime2", True), ("timestamp", "timestamp(6)", True),
    ("boolean", "bit", True), ("boolean", "bool", True),
    ("integer", "Nullable(Int32)", True), ("integer", "uint64", True), ("string", "LowCardinality(Nullable(String))", True),
    ("number", "Nullable(Decimal(12, 2))", True), ("timestamp", "DateTime64(6)", True), ("date", "Date32", True),
    ("string", "Nullable(Int32)", False), ("timestamp", "seconddate", True), ("string", "alphanum", True),
])
def test_type_matches(logical, physical, ok):
    assert type_matches(logical, physical) is ok


def test_type_matches_unknown():
    assert type_matches("object", "jsonb") is None
    assert type_matches("integer", "") is None


@pytest.mark.parametrize("name,quoted_status,table", [
    ("postgres", '"status"', '"odcr_meta"."validation_runs"'),
    ("mysql", "`status`", "`odcr_meta`.`validation_runs`"),
    ("sqlserver", "[status]", "[odcr_meta].[validation_runs]"),
    ("snowflake", '"STATUS"', "odcr_meta.validation_runs"),
    ("oracle", '"STATUS"', "odcr_meta_validation_runs"),
    ("sqlite", '"status"', '"odcr_meta_validation_runs"'),
    ("databricks", "`status`", "`odcr_meta`.`validation_runs`"),
    ("bigquery", "`status`", "`odcr_meta`.`validation_runs`"),
])
def test_quoting_and_meta_tables(name, quoted_status, table):
    a = make(name)
    assert a.quote("status") == quoted_status
    assert a.meta_table("odcr_meta", "validation_runs") == table


def test_quote_policy_needed_keeps_simple_names_unquoted():
    a = make("snowflake")
    assert a.quote("orders") == "orders"
    assert a.quote("Order Lines") == '"Order Lines"'
    assert a.qualify("sales.orders") == "sales.orders"


@pytest.mark.parametrize("name,expected", [
    ("postgres", "SELECT x FROM t LIMIT 5"), ("sqlserver", "SELECT TOP 5 x FROM t"),
    ("oracle", "SELECT x FROM t FETCH FIRST 5 ROWS ONLY"), ("db2", "SELECT x FROM t FETCH FIRST 5 ROWS ONLY"),
    ("teradata", "SELECT TOP 5 x FROM t"), ("clickhouse", "SELECT x FROM t LIMIT 5"),
    ("saphana", "SELECT x FROM t LIMIT 5"), ("hive", "SELECT x FROM t LIMIT 5"),
])
def test_limit(name, expected):
    assert make(name).limit("SELECT x FROM t", 5) == expected


def test_sqlserver_distinct_limit_and_clients():
    assert make("sqlserver").limit("SELECT DISTINCT x FROM t", 3) == "SELECT DISTINCT TOP 3 x FROM t"
    assert make("sqlserver").paramstyle == "qmark"
    assert make("sqlserver", client="pytds").paramstyle == "format"


def test_binding_styles():
    named = make("oracle")
    sql, params = named._bind(f"a = {named.placeholder} AND b = {named.placeholder}", [1, "x"])
    assert sql == "a = :p0 AND b = :p1" and params == {"p0": 1, "p1": "x"}
    inline = make("athena")
    sql, params = inline._bind(f"a = {inline.placeholder} AND b = {inline.placeholder} AND c = {inline.placeholder}",
                               ["it's", None, dt.date(2026, 1, 2)])
    assert sql == "a = 'it''s' AND b = NULL AND c = DATE '2026-01-02'" and params is None
    fmt = make("postgres")
    assert fmt._bind("a = %s", [1]) == ("a = %s", (1,))
    assert fmt._bind("a = 1", None) == ("a = 1", None)


def test_literals():
    a = make("athena")
    assert a.literal(True) == "TRUE"
    assert a.literal(Decimal("1.5")) == "1.5"
    assert a.literal(dt.datetime(2026, 1, 2, 3, 4, 5)) == "TIMESTAMP '2026-01-02 03:04:05.000000'"


def test_raw_relations_are_not_quoted():
    a = make("duckdb")
    assert a.qualify("read_parquet('x/*.parquet')") == "read_parquet('x/*.parquet')"
    assert a.relation("orders", "load_id = '1'") == "(SELECT * FROM \"orders\" WHERE load_id = '1') src"


def test_files_adapter_paths():
    a = make("files")
    assert a.to_relation("abfss://c@acc.dfs.core.windows.net/o/*.parquet").startswith("read_parquet('abfss://")
    assert a.to_relation("landing/o.csv") == "read_csv_auto('landing/o.csv')"
    assert a.to_relation("landing/o.jsonl") == "read_json_auto('landing/o.jsonl')"
    assert a.to_relation(r"C:\landing\o.csv").startswith("read_csv_auto(")
    assert a.to_relation("orders") == '"orders"'
    assert make("files", format="csv").reader("x/*") == "read_csv_auto"


def contract():
    return parse_contract({"apiVersion": "v3.0.2", "kind": "DataContract", "id": "c", "version": "1", "schema": [{
        "name": "orders", "physicalName": "sales.orders",
        "properties": [
            {"name": "id", "primaryKey": True},
            {"name": "status", "quality": [{"type": "library", "metric": "invalidValues",
                                            "arguments": {"validValues": ["A", "B"]}}]},
            {"name": "note", "quality": [{"type": "library", "metric": "missingValues",
                                          "arguments": {"missingValues": [None, "", "n/a"]}}]},
        ],
        "quality": [
            {"type": "library", "metric": "rowCount", "mustBeGreaterThan": 0},
            {"type": "library", "metric": "duplicateValues", "arguments": {"properties": ["id", "status"]}},
            {"type": "sql", "query": "SELECT COUNT(*) FROM ${object} WHERE x < 0"},
            {"type": "text", "description": "documented only"},
        ]}]})


def test_build_checks():
    checks = build_checks(contract().schema[0], where="load_id = '1'")
    assert [c.check_id for c in checks] == ["orders.id.required", "orders.id.unique", "orders.status.invalidValues",
                                            "orders.note.missingValues", "orders.rowCount", "orders.duplicateValues",
                                            "orders.sql_3"]
    assert all(c.where == "load_id = '1'" and c.physical_name == "sales.orders" for c in checks)


@pytest.mark.parametrize("name", ["postgres", "mysql", "sqlserver", "oracle", "snowflake", "databricks", "bigquery",
                                  "trino", "duckdb", "sqlite", "db2", "redshift", "athena", "synapse", "fabric",
                                  "clickhouse", "vertica", "teradata", "saphana", "hive", "impala"])
def test_metric_sql_for_every_sql_adapter(name):
    a = make(name)
    obj = contract().schema[0]
    for check in build_checks(obj, where="load_id = '1'"):
        if check.metric:
            sql, params = a.metric_sql(check.metric, check.physical_name, check.where, check.column, check.args)
            assert sql.startswith("SELECT") and "load_id = '1'" in sql
            assert sql.count(a.placeholder) == len(params)
        else:
            assert "load_id = '1'" in a.render_query(check.query, check.physical_name, check.where, check.column)


def test_sql_adapter_rejects_other_engines():
    a = make("postgres")
    with pytest.raises(UnsupportedCheck):
        a.evaluate(Check("x", "custom", "o", "o", None, "error", query="{}", engine="mongodb"))


@pytest.mark.parametrize("name,marker", [("postgres", "CREATE TABLE IF NOT EXISTS"), ("mysql", "DATETIME(6)"),
                                         ("sqlserver", "IF OBJECT_ID("), ("synapse", "WITH (HEAP)"),
                                         ("fabric", "DATETIME2(6)"), ("databricks", "USING DELTA"),
                                         ("oracle", "VARCHAR2(4000)"), ("snowflake", "TIMESTAMP_NTZ"),
                                         ("bigquery", "INT64"), ("redshift", "VARCHAR(65535)"), ("db2", "CREATE TABLE"),
                                         ("trino", "TIMESTAMP(6)"), ("sqlite", "TEXT"), ("duckdb", "VARCHAR"),
                                         ("clickhouse", "ENGINE = MergeTree"), ("vertica", "CREATE SCHEMA IF NOT EXISTS"),
                                         ("teradata", "MULTISET"), ("saphana", "CREATE COLUMN TABLE"),
                                         ("hive", "STRING"), ("impala", "BIGINT")])
def test_meta_ddl_per_dialect(name, marker):
    stmts = ddl(make(name), "odcr_meta")
    assert sum(1 for s in stmts if " TABLE " in s) == len(TABLES)
    assert any(marker in s for s in stmts)


def test_document_helpers():
    assert parse_filter('{"a": 1}') == {"a": 1}
    assert parse_filter(None) == {}
    with pytest.raises(ValueError, match="JSON"):
        parse_filter("a = 1")
    with pytest.raises(ValueError):
        parse_filter("[1]")
    cols = infer_columns([{"_id": 1, "a": 1, "b": "x", "c": None, "d": dt.datetime(2026, 1, 1)}, {"a": 2.5}], ("_id",))
    assert cols == {"a": "int64", "b": "string", "c": "", "d": "bsondate"}


def test_cosmos_query_builders():
    assert prop("a.b") == 'c["a"]["b"]'
    assert is_null("x") == '(NOT IS_DEFINED(c["x"]) OR IS_NULL(c["x"]))'
    assert where_clause(None, "c.a = 1") == " WHERE (c.a = 1)"
    a = CosmosDBAdapter()
    sql, params = a.metric_query(Check("i", "quality", "o", "o", "status", "error", where="c.load_id = '1'",
                                       metric="invalidValues", args={"validValues": ["A"]}))
    assert "ARRAY_CONTAINS(@valid" in sql and "c.load_id = '1'" in sql and params[0]["value"] == ["A"]
    sql, _ = a.metric_query(Check("d", "quality", "o", "o", None, "error", metric="duplicateValues",
                                  args={"properties": ["a", "b"]}))
    assert 'GROUP BY c["a"], c["b"]' in sql


def test_new_dialect_literals():
    import datetime as dt
    ch = make("clickhouse")
    assert ch.literal("a'b\\c") == "'a\\'b\\\\c'"
    assert ch.literal(dt.datetime(2026, 1, 2, 3, 4, 5)) == "toDateTime64('2026-01-02 03:04:05.000000', 6)"
    assert ch.literal(dt.date(2026, 1, 2)) == "toDate('2026-01-02')"
    assert make("impala").literal(dt.date(2026, 1, 2)) == "CAST('2026-01-02' AS DATE)"
    assert make("teradata").limit("SELECT DISTINCT x FROM t", 3) == "SELECT DISTINCT TOP 3 x FROM t"
    assert make("teradata").meta_table("odcr_meta", "validation_runs") == "odcr_meta_validation_runs"


def test_kafka_and_event_hubs_settings():
    k = make("kafka", bootstrap_servers="b:9092", security_protocol="SASL_SSL", sasl_mechanism="PLAIN",
             config={"linger.ms": 5})
    conf = k.consumer_config()
    assert conf["bootstrap.servers"] == "b:9092" and conf["security.protocol"] == "SASL_SSL"
    assert conf["linger.ms"] == 5 and conf["group.id"] == "odcr" and conf["enable.auto.commit"] is False
    assert {"_kafka_offset", "_kafka_key"} <= set(k.system_columns())
    eh = make("eventhubs", namespace="mybus", connection_string="Endpoint=sb://mybus/;SharedAccessKey=x")
    conf = eh.consumer_config()
    assert conf["bootstrap.servers"] == "mybus.servicebus.windows.net:9093"
    assert conf["sasl.username"] == "$ConnectionString" and conf["group.id"] == "$Default"
    assert make("eventhubs", namespace="mybus", consumer_group="odcr", mock=True).consumer_config()["group.id"] == "odcr"


def test_kafka_micro_batches_and_invalid_messages():
    from odcr.adapters.kafka import MemoryKafka

    a = get_adapter({"type": "kafka", "mock": True, "group_id": "unit"})
    a.connect()
    a.create_sample("unit_topic", [("id", "integer"), ("name", "string")], [(1, "a"), (2, "b")])
    MemoryKafka.Producer({}).produce("unit_topic", b"not json")
    assert a.count("unit_topic") == 3
    assert a.count("unit_topic", "_kafka_value IS NOT NULL") == 1
    assert {"id", "name", "_kafka_partition"} <= set(a.columns("unit_topic"))
    a.close()
    a.connect()  # a new run only sees messages that arrived since the last one
    assert a.count("unit_topic") == 0
    a.create_sample("unit_topic", [("id", "integer"), ("name", "string")], [(3, "c")])
    assert a.count("unit_topic") == 1
    assert a.columns("missing_topic") == {}
    a.drop_table("unit_topic")
    a.close()


def test_sqlserver_windows_authentication(monkeypatch):
    import sys
    import types
    seen = {}
    fake = types.SimpleNamespace(connect=lambda cs, autocommit: seen.setdefault("cs", cs))
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    make("sqlserver", host="sql01", database="dw", trusted_connection="yes")._connect()
    assert "Trusted_Connection=yes" in seen["cs"] and "UID=" not in seen["cs"]
