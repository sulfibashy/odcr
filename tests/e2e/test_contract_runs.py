"""End-to-end: run contracts against live PostgreSQL / MySQL (and SQL Server when configured)."""

from __future__ import annotations

import pytest

from odcr.contract import parse_contract
from odcr.meta import table_name as meta_table
from odcr.runner import run_contract
from tests.conftest import BAD_ROWS, GOOD_ROWS, contract_doc, create_orders, drop_table

pytestmark = pytest.mark.e2e


def _count(db, schema, table, where="1=1", params=None):
    return int(db.scalar(f"SELECT COUNT(*) FROM {meta_table(db, schema, table)} WHERE {where}", params))


def test_good_batch_passes_and_is_logged(db, config, table_name, webhook):
    create_orders(db, table_name, GOOD_ROWS)
    try:
        contract = parse_contract(contract_doc(table_name, webhook.url))
        result = run_contract(contract, db, config, batch_id="A")
        assert result.status == "pass", result.summary()
        run = result.objects[0]
        assert run.rows_checked == 4
        assert not run.failed and not run.warned
        p = db.placeholder
        assert _count(db, config.meta_schema, "validation_runs", f"run_id = {p} AND status = 'pass'",
                      [run.run_id]) == 1
        assert _count(db, config.meta_schema, "check_results", f"run_id = {p}", [run.run_id]) == len(run.results)
        assert _count(db, config.meta_schema, "quarantine_log", f"run_id = {p}", [run.run_id]) == 0
        assert _count(db, config.meta_schema, "contracts", f"yaml_hash = {p}", [contract.yaml_hash]) == 1
        assert webhook.calls == []  # nothing to report
    finally:
        drop_table(db, table_name)


def test_bad_batch_fails_quarantines_and_notifies(db, config, table_name, webhook):
    create_orders(db, table_name, BAD_ROWS)
    try:
        contract = parse_contract(contract_doc(table_name, webhook.url))
        result = run_contract(contract, db, config, batch_id="B")
        assert result.status == "fail"
        run = result.objects[0]
        failed = {r.check_id for r in run.failed}
        assert failed == {
            "orders.customer_id.required",
            "orders.order_id.unique",
            "orders.status.invalidValues",
            "orders.no_negative_amounts",
        }, result.summary()
        by_id = {r.check_id: r for r in run.results}
        assert by_id["orders.order_id.unique"].actual == "1"
        assert by_id["orders.status.invalidValues"].actual == "1"
        p = db.placeholder
        assert _count(db, config.meta_schema, "quarantine_log", f"run_id = {p} AND batch_id = 'B'",
                      [run.run_id]) == 1
        assert _count(db, config.meta_schema, "check_results", f"run_id = {p} AND status = 'failed'",
                      [run.run_id]) == 4
        # source team (from contract) and platform team (from config) are both notified and logged
        assert sorted(c["path"] for c in webhook.calls) == ["/platform", "/source"]
        assert "orders.status.invalidValues" in webhook.calls[0]["json"]["text"]
        assert [d.status for d in result.notifications] == ["sent", "sent"]
        assert _count(db, config.meta_schema, "notifications", f"run_id = {p} AND status = 'sent'",
                      [run.run_id]) == 2
    finally:
        drop_table(db, table_name)


def test_warning_does_not_fail_or_quarantine(db, config, table_name, webhook):
    rows = GOOD_ROWS + [(5, 104, "NEW", None, "2026-11-02", "A")]  # 20% NULL amount, rule is a warning
    create_orders(db, table_name, rows)
    try:
        result = run_contract(parse_contract(contract_doc(table_name, webhook.url)), db, config, batch_id="A")
        assert result.status == "warn", result.summary()
        run = result.objects[0]
        assert [r.check_id for r in run.warned] == ["orders.amount.nullValues"]
        assert run.warned[0].actual == "20%"
        assert _count(db, config.meta_schema, "quarantine_log", f"run_id = {db.placeholder}", [run.run_id]) == 0
        assert len(webhook.calls) == 2  # notify_on includes warn
    finally:
        drop_table(db, table_name)


def test_same_rule_as_error_fails(db, config, table_name, webhook):
    rows = GOOD_ROWS + [(5, 104, "NEW", None, "2026-11-02", "A")]
    create_orders(db, table_name, rows)
    try:
        doc = contract_doc(table_name, webhook.url, amount_null_severity="error")
        result = run_contract(parse_contract(doc), db, config, batch_id="A")
        assert result.status == "fail"
    finally:
        drop_table(db, table_name)


def test_batch_filter_checks_only_that_batch(db, config, table_name, webhook):
    create_orders(db, table_name, GOOD_ROWS + BAD_ROWS)
    try:
        contract = parse_contract(contract_doc(table_name, webhook.url))
        good = run_contract(contract, db, config, batch_id="A", where="load_id = 'A'")
        bad = run_contract(contract, db, config, batch_id="B", where="load_id = 'B'")
        assert good.status == "pass" and good.objects[0].rows_checked == 4
        assert bad.status == "fail" and bad.objects[0].rows_checked == 4
    finally:
        drop_table(db, table_name)


def test_schema_drift_is_caught(db, config, table_name, webhook):
    # order_date missing, extra column added, amount stored as text
    text = "NVARCHAR(20)" if db.dialect == "sqlserver" else "VARCHAR(20)"
    rows = [(1, 101, "NEW", "10.5", "A", "X1")]
    create_orders(db, table_name, rows, extra_column=True, drop_column="order_date", amount_type=text)
    try:
        result = run_contract(parse_contract(contract_doc(table_name, webhook.url)), db, config)
        run = result.objects[0]
        status = {r.check_id: r.status for r in run.results}
        assert result.status == "fail"
        assert status["orders.order_date.exists"] == "failed"
        assert status["orders.amount.type"] == "failed"
        assert status["orders.order_date.required"] == "skipped"
        assert status["orders.no_extra_columns"] == "warning"
        assert status["orders.order_id.type"] == "passed"
    finally:
        drop_table(db, table_name)


def test_missing_table(db, config, webhook):
    result = run_contract(parse_contract(contract_doc("table_that_does_not_exist", webhook.url)), db, config)
    run = result.objects[0]
    assert result.status == "fail"
    assert [r.check_id for r in run.failed] == ["orders.exists"]
    assert run.rows_checked is None


def test_broken_sql_check_is_an_error_not_a_crash(db, config, table_name, webhook):
    create_orders(db, table_name, GOOD_ROWS)
    try:
        doc = contract_doc(table_name, webhook.url)
        doc["schema"][0]["quality"].append({"type": "sql", "name": "broken", "query": "SELECT nonsense FROM"})
        result = run_contract(parse_contract(doc), db, config)
        res = {r.check_id: r for r in result.objects[0].results}["broken"]
        assert res.status == "error" and "could not run" in res.message
        assert result.status == "fail"
    finally:
        drop_table(db, table_name)


def test_on_fail_log_skips_quarantine_and_contract_registered_once(db, config, table_name, webhook):
    create_orders(db, table_name, BAD_ROWS)
    try:
        config.on_fail = "log"
        contract = parse_contract(contract_doc(table_name, webhook.url))
        r1 = run_contract(contract, db, config, send_notifications=False)
        run_contract(contract, db, config, send_notifications=False)
        p = db.placeholder
        assert _count(db, config.meta_schema, "quarantine_log", f"run_id = {p}", [r1.objects[0].run_id]) == 0
        assert _count(db, config.meta_schema, "contracts", f"yaml_hash = {p}", [contract.yaml_hash]) == 1
        assert webhook.calls == []
    finally:
        drop_table(db, table_name)
