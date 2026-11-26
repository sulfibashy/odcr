import pytest

from odcr.adapters import MySQLAdapter, PostgresAdapter, SQLServerAdapter, get_adapter, type_matches
from odcr.checks import build_checks, compare, describe_expectation, relation
from odcr.contract import parse_contract
from odcr.meta import TABLES, ddl


@pytest.mark.parametrize("comp,actual,thr,ok", [
    ("mustBe", 0, 0, True), ("mustBe", 1, 0, False),
    ("mustNotBe", 1, 0, True), ("mustNotBe", 0, 0, False),
    ("mustBeGreaterThan", 5, 4, True), ("mustBeGreaterThan", 4, 4, False),
    ("mustBeGreaterOrEqualTo", 4, 4, True), ("mustBeGreaterThanOrEqualTo", 3, 4, False),
    ("mustBeLessThan", 3, 4, True), ("mustBeLessThan", 4, 4, False),
    ("mustBeLessOrEqualTo", 4, 4, True), ("mustBeLessThanOrEqualTo", 5, 4, False),
    ("mustBeBetween", 5, [1, 10], True), ("mustBeBetween", 11, [1, 10], False),
    ("mustNotBeBetween", 11, [1, 10], True), ("mustNotBeBetween", 5, [1, 10], False),
    (None, 123, None, True),
])
def test_compare(comp, actual, thr, ok):
    assert compare(comp, actual, thr) is ok


def test_compare_unknown():
    with pytest.raises(ValueError):
        compare("mustBeAwesome", 1, 1)


def test_describe_expectation():
    assert describe_expectation("mustBe", 0) == "= 0"
    assert describe_expectation("mustBeLessOrEqualTo", 1, "percent") == "<= 1%"
    assert describe_expectation("mustNotBeBetween", [1, 2]) == "not between 1 and 2"
    assert describe_expectation(None, None) == ""


@pytest.mark.parametrize("logical,physical,ok", [
    ("integer", "integer", True), ("integer", "bigint", True), ("integer", "varchar", False),
    ("number", "numeric", True), ("number", "decimal", True), ("number", "double precision", True),
    ("string", "character varying", True), ("string", "nvarchar", True), ("string", "int", False),
    ("date", "date", True), ("date", "datetime", False),
    ("timestamp", "timestamp without time zone", True), ("timestamp", "datetime2", True),
    ("boolean", "bit", True), ("boolean", "boolean", True),
])
def test_type_matches(logical, physical, ok):
    assert type_matches(logical, physical) is ok


def test_type_matches_unknown_is_none():
    assert type_matches("object", "jsonb") is None
    assert type_matches(None, "int") is None


@pytest.mark.parametrize("cls,q", [(PostgresAdapter, '"'), (MySQLAdapter, "`"), (SQLServerAdapter, "[")])
def test_quoting_and_relation(cls, q):
    a = cls()
    assert a.qualify("sales.orders").startswith(q)
    assert relation(a, "orders").endswith(" src")
    assert "WHERE load_id = 'A'" in relation(a, "orders", "load_id = 'A'")


def test_sqlserver_limit_and_placeholders():
    a = SQLServerAdapter()
    assert a.limit("SELECT x FROM t", 5) == "SELECT TOP 5 x FROM t"
    assert a.params(3) == "?, ?, ?"
    assert PostgresAdapter().limit("SELECT x FROM t", 5) == "SELECT x FROM t LIMIT 5"


def test_build_checks_from_contract():
    doc = {"apiVersion": "v3.0.2", "kind": "DataContract", "id": "c", "version": "1", "schema": [{
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
        ]}]}
    a = PostgresAdapter()
    checks = build_checks(a, parse_contract(doc).schema[0], where="load_id = '1'")
    ids = [c.check_id for c in checks]
    assert ids == ["orders.id.required", "orders.id.unique", "orders.status.invalidValues",
                   "orders.note.missingValues", "orders.rowCount", "orders.duplicateValues", "orders.sql_3"]
    inval = checks[2]
    assert inval.params == ["A", "B"] and "NOT IN (%s, %s)" in inval.sql
    assert checks[3].params == ["", "n/a"]
    assert 'GROUP BY "id", "status"' in checks[5].sql
    assert '"sales"."orders"' in checks[6].sql and "load_id = '1'" in checks[6].sql


def test_object_duplicate_without_properties_fails():
    doc = {"apiVersion": "v3", "kind": "DataContract", "id": "c", "version": "1", "schema": [{
        "name": "t", "quality": [{"type": "library", "metric": "duplicateValues"}]}]}
    with pytest.raises(ValueError):
        build_checks(PostgresAdapter(), parse_contract(doc).schema[0])


@pytest.mark.parametrize("cls,marker", [(PostgresAdapter, "CREATE TABLE IF NOT EXISTS"),
                                        (MySQLAdapter, "DATETIME(6)"),
                                        (SQLServerAdapter, "IF OBJECT_ID(")])
def test_meta_ddl_per_dialect(cls, marker):
    stmts = ddl(cls(), "odcr_meta")
    assert len(stmts) == len(TABLES)
    assert all(marker in s for s in stmts) or any(marker in s for s in stmts)
    for table in TABLES:
        assert any(table in s for s in stmts)


def test_get_adapter():
    assert isinstance(get_adapter({"type": "postgresql"}), PostgresAdapter)
    assert isinstance(get_adapter({"type": "MariaDB"}), MySQLAdapter)
    assert isinstance(get_adapter({"type": "mssql"}), SQLServerAdapter)
    with pytest.raises(ValueError):
        get_adapter({"type": "oracle"})
