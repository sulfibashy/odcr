import pytest

from odcr import notify
from odcr.config import ConfigError, interpolate, load_config, parse_config
from odcr.contract import Contact, ContractError
from odcr.reconcile import ReconCheck, _compare, parse_reconciliation


def test_interpolation(monkeypatch):
    monkeypatch.setenv("HOST_X", "db.example")
    assert interpolate("${HOST_X}:${PORT_X:-5432}") == "db.example:5432"
    assert interpolate({"a": ["${MISSING_X}"]}) == {"a": [""]}
    assert interpolate(5) == 5


def test_parse_config_defaults_and_errors():
    c = parse_config({"connections": {"pg": {"type": "postgres"}}})
    assert c.meta_schema == "odcr_meta" and c.notify_on == ["fail"] and c.on_fail == "quarantine"
    assert c.connection("pg")["type"] == "postgres"
    with pytest.raises(ConfigError):
        c.connection("nope")
    with pytest.raises(ConfigError):
        parse_config({"connections": {"pg": {"host": "x"}}})
    with pytest.raises(ConfigError):
        parse_config({"connections": ["x"]})


def test_load_config_file(tmp_path, monkeypatch):
    p = tmp_path / "odcr.yaml"
    p.write_text("connections:\n  a: {type: mysql, password: '${PW_X:-secret}'}\nmeta: {schema: m}\n")
    c = load_config(p)
    assert c.connection("a")["password"] == "secret" and c.meta_schema == "m"
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")
    monkeypatch.chdir(tmp_path)
    assert load_config(None).meta_schema == "m"  # picks up ./odcr.yaml


def test_recipients_and_mask():
    r = notify.recipients(
        [Contact("slack", "https://hooks.slack.com/services/T/B/secret"), Contact("email", "src@x.com")],
        [{"type": "teams", "url": "https://teams.example/hook"}, {"type": "email", "to": ["p@x.com", "q@x.com"]},
         {"type": "console"}, {"type": "slack"}])  # slack without url is ignored
    assert [(x.channel, x.audience) for x in r] == [
        ("slack", "source"), ("email", "source"), ("teams", "platform"), ("email", "platform"),
        ("email", "platform"), ("console", "platform")]
    assert notify.mask("https://hooks.slack.com/services/T/B/secret") == "https://hooks.slack.com/***"
    assert notify.mask("a@b.com") == "a@b.com"


def test_send_webhooks_and_failures(webhook, capsys):
    recips = [notify.Recipient("slack", f"{webhook.url}/s", "source"),
              notify.Recipient("teams", f"{webhook.url}/t", "platform"),
              notify.Recipient("webhook", "http://127.0.0.1:9/unreachable", "platform"),
              notify.Recipient("console", "stdout", "platform"),
              notify.Recipient("carrier-pigeon", "x", "platform")]
    out = notify.send(recips, "subject", "body", {"k": 1})
    assert [d.status for d in out] == ["sent", "sent", "failed", "sent", "failed"]
    paths = {c["path"]: c["json"] for c in webhook.calls}
    assert paths["/s"]["text"].startswith("*subject*")
    assert paths["/t"]["title"] == "subject"
    assert "subject" in capsys.readouterr().out


def test_email_failure_is_recorded():
    out = notify.send([notify.Recipient("email", "a@b.com", "platform")], "s", "b", {},
                      smtp={"host": "127.0.0.1", "port": 9})
    assert out[0].status == "failed" and out[0].error


def test_parse_reconciliation():
    r = parse_reconciliation({"id": "r", "source": {"object": "a"}, "target": {"object": "b"},
                              "checks": [{"type": "rowCount"}, {"type": "sum", "column": "x", "tolerance": 0.5},
                                         {"type": "sum", "sourceColumn": "x", "targetColumn": "y"}]})
    assert [c.check_id for c in r.checks] == ["rowCount", "sum(x)", "sum(x)"]
    assert r.checks[2].target_column == "y"
    default = parse_reconciliation({"id": "r", "source": {"object": "a"}, "target": {"object": "b"}})
    assert [c.type for c in default.checks] == ["rowCount"]


@pytest.mark.parametrize("doc,problem", [
    ({"source": {"object": "a"}, "target": {"object": "b"}}, "missing 'id'"),
    ({"id": "r", "target": {"object": "b"}}, "source needs"),
    ({"id": "r", "source": {"object": "a"}, "target": {"object": "b"}, "checks": [{"type": "avg"}]}, "unknown type"),
    ({"id": "r", "source": {"object": "a"}, "target": {"object": "b"}, "checks": [{"type": "sum"}]}, "needs 'column'"),
    ({"id": "r", "kind": "X", "source": {"object": "a"}, "target": {"object": "b"}}, "kind must be"),
])
def test_parse_reconciliation_errors(doc, problem):
    with pytest.raises(ContractError) as exc:
        parse_reconciliation(doc)
    assert any(problem in p for p in exc.value.problems)


@pytest.mark.parametrize("check,s,t,status", [
    (ReconCheck("rowCount"), 10, 10, "passed"),
    (ReconCheck("rowCount"), 10, 9, "failed"),
    (ReconCheck("sum", "x", "x", tolerance=0.01), 100.00, 100.005, "passed"),
    (ReconCheck("sum", "x", "x", tolerance=0.01), 100.00, 100.5, "failed"),
    (ReconCheck("sum", "x", "x", tolerance_percent=1.0), 100.0, 100.9, "passed"),
    (ReconCheck("max", "d", "d"), "2026-01-01", "2026-01-01", "passed"),
    (ReconCheck("max", "d", "d"), "2026-01-01", "2026-01-02", "failed"),
    (ReconCheck("sum", "x", "x"), None, None, "passed"),
])
def test_recon_compare(check, s, t, status):
    assert _compare(check, s, t).status == status
