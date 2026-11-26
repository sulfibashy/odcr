import pytest
import yaml

from odcr.adapters import resolve
from odcr.contract import ContractError, load_contract, parse_contract
from odcr.scaffold import contract_yaml


def base_doc(**overrides):
    doc = {"apiVersion": "v3.0.2", "kind": "DataContract", "id": "c1", "version": "1.0.0",
           "schema": [{"name": "t", "properties": [{"name": "a", "logicalType": "integer"}]}]}
    doc.update(overrides)
    return doc


@pytest.mark.parametrize("adapter", ["postgres", "mongodb", "cosmosdb", "files"])
def test_generated_contract_loads(adapter):
    c = parse_contract(yaml.safe_load(contract_yaml(resolve(adapter))))
    assert c.id == "orders" and c.owner == "order-team-lead"
    assert [p.name for p in c.schema[0].properties][:2] == ["order_id", "customer_id"]
    kinds = {r.type for r in c.schema[0].quality}
    assert kinds == ({"library", "custom"} if adapter in ("mongodb", "cosmosdb") else {"library", "sql"})


def test_hash_changes_with_content(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(base_doc()))
    h1 = load_contract(p).yaml_hash
    p.write_text(yaml.safe_dump(base_doc(version="1.0.1")))
    assert load_contract(p).yaml_hash != h1


@pytest.mark.parametrize("missing", ["apiVersion", "kind", "id", "version", "schema"])
def test_required_fields(missing):
    doc = base_doc()
    doc.pop(missing)
    with pytest.raises(ContractError) as exc:
        parse_contract(doc)
    assert any(missing in p for p in exc.value.problems)


def test_rejects_non_v3_and_wrong_kind():
    with pytest.raises(ContractError) as exc:
        parse_contract(base_doc(apiVersion="v2.2.2", kind="Other"))
    joined = " ".join(exc.value.problems)
    assert "not ODCS v3" in joined and "kind must be DataContract" in joined


def test_odcs_30_rule_aliases_and_default_comparator():
    doc = base_doc()
    doc["schema"][0]["properties"][0]["quality"] = [
        {"rule": "nullCheck"}, {"rule": "duplicateCount", "mustBeLessThan": 2}, {"rule": "validValues", "validValues": [1, 2]}]
    rules = parse_contract(doc).schema[0].properties[0].quality
    assert [r.metric for r in rules] == ["nullValues", "duplicateValues", "invalidValues"]
    assert (rules[0].comparator, rules[0].threshold) == ("mustBe", 0)
    assert (rules[1].comparator, rules[1].threshold) == ("mustBeLessThan", 2)
    assert rules[2].arguments["validValues"] == [1, 2]


@pytest.mark.parametrize("rule,problem", [
    ({"type": "library"}, "needs 'metric'"),
    ({"type": "library", "metric": "nope"}, "unsupported metric"),
    ({"type": "library", "metric": "invalidValues"}, "validValues"),
    ({"type": "sql"}, "needs 'query'"),
    ({"type": "weird"}, "unknown quality type"),
    ({"type": "library", "metric": "rowCount"}, "rowCount needs a comparator"),
    ({"type": "library", "metric": "nullValues", "mustBeBetween": 3}, "list of two numbers"),
    ({"type": "custom", "engine": "mongodb"}, "needs 'implementation'"),
])
def test_invalid_quality_rules(rule, problem):
    doc = base_doc()
    doc["schema"][0]["quality"] = [rule]
    with pytest.raises(ContractError) as exc:
        parse_contract(doc)
    assert any(problem in p for p in exc.value.problems), exc.value.problems


def test_custom_rule_defaults():
    doc = base_doc()
    doc["schema"][0]["quality"] = [{"type": "custom", "engine": "MongoDB", "implementation": '{"a": 1}'},
                                   {"type": "custom", "description": "documented only"}]
    r = parse_contract(doc).schema[0].quality
    assert (r[0].engine, r[0].comparator, r[0].threshold) == ("mongodb", "mustBe", 0)
    assert r[1].engine is None and r[1].comparator is None


@pytest.mark.parametrize("value,expected", [("warning", "warning"), ("warn", "warning"), ("info", "warning"),
                                            ("error", "error"), ("critical", "error"), (None, "error")])
def test_severity_mapping(value, expected):
    doc = base_doc()
    rule = {"type": "library", "metric": "nullValues"}
    if value:
        rule["severity"] = value
    doc["schema"][0]["properties"][0]["quality"] = [rule]
    assert parse_contract(doc).schema[0].properties[0].quality[0].severity == expected


def test_support_channels(monkeypatch):
    monkeypatch.setenv("SRC_HOOK", "https://hooks.example.com/abc")
    doc = base_doc(support=[
        {"channel": "#a", "tool": "slack", "url": "${SRC_HOOK}"},
        {"channel": "#b", "tool": "teams", "url": "${UNSET_HOOK_X}"},  # empty -> skipped
        {"channel": "t", "tool": "MSTeams", "url": "https://teams.example/hook"},
        {"channel": "team@example.com", "tool": "email"},
        {"channel": "x", "tool": "mail", "url": "mailto:x@example.com"},
        {"channel": "g", "tool": "google_chat", "url": "https://chat.example/hook"},
        {"channel": "pd", "tool": "pagerduty", "url": "routingkey123"},
        {"channel": "o", "tool": "opsgenie", "url": "geniekey123"},
        {"channel": "d", "tool": "discord", "url": "https://discord.example/hook"},
        {"channel": "j", "tool": "jira", "url": "https://jira.example"},  # unknown tool -> ignored
    ])
    assert [(c.kind, c.target) for c in parse_contract(doc).contacts] == [
        ("slack", "https://hooks.example.com/abc"), ("teams", "https://teams.example/hook"),
        ("email", "team@example.com"), ("email", "x@example.com"), ("googlechat", "https://chat.example/hook"),
        ("pagerduty", "routingkey123"), ("opsgenie", "geniekey123"), ("discord", "https://discord.example/hook")]


def test_missing_file_and_bad_yaml(tmp_path):
    with pytest.raises(ContractError):
        load_contract(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    with pytest.raises(ContractError):
        load_contract(bad)


def test_object_lookup_by_physical_name():
    doc = base_doc()
    doc["schema"][0]["physicalName"] = "sales.t_raw"
    c = parse_contract(doc)
    assert c.object("sales.t_raw").name == "t"
    with pytest.raises(KeyError):
        c.object("missing")
