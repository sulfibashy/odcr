import os
import socketserver
import sys
import threading
import types

import pytest

from odcr import notify
from odcr.config import ConfigError, interpolate, load_config, load_dotenv, parse_config
from odcr.contract import Contact, ContractError
from odcr.reconcile import ReconCheck, _compare, parse_reconciliation


def test_interpolation(monkeypatch, tmp_path):
    monkeypatch.setenv("HOST_X", "db.example")
    assert interpolate("${HOST_X}:${PORT_X:-5432}") == "db.example:5432"
    assert interpolate({"a": ["${MISSING_X}"]}) == {"a": [""]}
    monkeypatch.setenv("EMPTY_X", "")
    assert interpolate("${EMPTY_X:-fallback}") == "fallback"  # empty value uses the default, like the shell
    assert interpolate("${EMPTY_X}") == ""
    secret = tmp_path / "pw"
    secret.write_text("s3cret\n")
    assert interpolate(f"${{file:{secret}}}") == "s3cret"
    assert interpolate(5) == 5


def test_parse_config_defaults_and_errors():
    c = parse_config({"connections": {"pg": {"type": "postgres"}}})
    assert c.meta_schema == "odcr_meta" and c.notify_on == ["fail"] and c.on_fail == "quarantine"
    assert c.contracts == {"path": "contracts"} and c.meta_connection is None
    with pytest.raises(ConfigError):
        c.connection("nope")
    with pytest.raises(ConfigError):
        parse_config({"connections": {"pg": {"host": "x"}}})
    with pytest.raises(ConfigError):
        parse_config({"connections": ["x"]})
    with pytest.raises(ConfigError, match="meta.connection"):
        parse_config({"connections": {"a": {"type": "sqlite"}}, "meta": {"connection": "b"}})
    assert parse_config({"contracts": "shared/contracts"}).contracts == {"path": "shared/contracts"}


def test_load_config_and_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("PW_X", raising=False)
    (tmp_path / ".env").write_text("# comment\nexport PW_X='from-dotenv'\nEMPTY_LINE_OK=\n")
    p = tmp_path / "odcr.yaml"
    p.write_text("connections:\n  a: {type: mysql, password: '${PW_X:-secret}'}\nmeta: {schema: m}\n")
    c = load_config(p)
    assert c.connection("a")["password"] == "from-dotenv" and c.meta_schema == "m"
    assert c.base_dir == tmp_path.resolve()
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")
    monkeypatch.chdir(tmp_path)
    assert load_config(None).meta_schema == "m"
    os.environ["KEEP_X"] = "env-wins"
    (tmp_path / ".env2").write_text("KEEP_X=file\n")
    load_dotenv(tmp_path / ".env2")
    assert os.environ["KEEP_X"] == "env-wins"


def test_recipients_and_mask():
    r = notify.recipients(
        [Contact("slack", "https://hooks.slack.com/services/T/B/secret"), Contact("email", "src@x.com")],
        [{"type": "MSTeams", "url": "https://teams.example/hook"}, {"type": "mail", "to": ["p@x.com", "q@x.com"]},
         {"type": "console"}, {"type": "slack"}, {"type": "pagerduty", "routing_key": "rk"},
         {"type": "opsgenie", "key": "gk"}])
    assert [(x.channel, x.audience) for x in r] == [
        ("slack", "source"), ("email", "source"), ("teams", "platform"), ("email", "platform"),
        ("email", "platform"), ("console", "platform"), ("pagerduty", "platform"), ("opsgenie", "platform")]
    assert notify.mask("https://hooks.slack.com/services/T/B/secret") == "https://hooks.slack.com/***"
    assert notify.mask("a@b.com") == "a@b.com"
    assert notify.mask("0123456789abcdef") == "0123***"


def test_every_channel_payload(webhook, capsys):
    settings = {"pagerduty_url": f"{webhook.url}/pd", "opsgenie_url": f"{webhook.url}/og"}
    recips = [notify.Recipient(c, f"{webhook.url}/{c}", "source")
              for c in ("slack", "teams", "googlechat", "discord", "webhook")]
    recips += [notify.Recipient("pagerduty", "routing-key-1", "platform"),
               notify.Recipient("opsgenie", "genie-key-1", "platform"),
               notify.Recipient("console", "stdout", "platform")]
    out = notify.send(recips, "subject", "body", {"status": "warn"}, settings)
    assert [d.status for d in out] == ["sent"] * len(recips)
    calls = {c["path"]: c for c in webhook.calls}
    assert calls["/slack"]["json"]["text"].startswith("*subject*")
    card = calls["/teams"]["json"]["attachments"][0]
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["content"]["body"][0]["text"] == "subject"
    assert calls["/googlechat"]["json"]["text"].startswith("*subject*")
    assert calls["/discord"]["json"]["content"].startswith("**subject**")
    assert calls["/webhook"]["json"]["subject"] == "subject"
    assert calls["/pd"]["json"]["routing_key"] == "routing-key-1"
    assert calls["/pd"]["json"]["payload"]["severity"] == "warning"
    assert calls["/og"]["headers"]["Authorization"] == "GenieKey genie-key-1"
    assert "subject" in capsys.readouterr().out


def test_failures_are_recorded_not_raised(tmp_path):
    bad_ca = tmp_path / "ca.pem"
    bad_ca.write_text("not a certificate")
    out = notify.send([notify.Recipient("webhook", "http://127.0.0.1:9/unreachable", "platform"),
                       notify.Recipient("carrier-pigeon", "x", "platform"),
                       notify.Recipient("slack", "https://127.0.0.1:9/x", "platform"),
                       notify.Recipient("email", "a@b.com", "platform")],
                      "s", "b", {}, {"ca_bundle": str(bad_ca), "smtp": {"host": "127.0.0.1", "port": 9}})
    assert [d.status for d in out] == ["failed"] * 4
    assert all(d.error for d in out)


def test_email_without_server_explains_itself():
    out = notify.send([notify.Recipient("email", "a@b.com", "platform")], "s", "b", {}, {"smtp": {"host": ""}})
    assert out[0].status == "failed" and "SMTP_HOST" in out[0].error


def test_ssl_context_options(tmp_path):
    ctx = notify._ssl_context({})
    assert ctx.verify_mode.name == "CERT_REQUIRED" and ctx.check_hostname
    insecure = notify._ssl_context({"verify": False})
    assert insecure.verify_mode.name == "CERT_NONE"


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
    (ReconCheck("rowCount"), 10, 10, "passed"), (ReconCheck("rowCount"), 10, 9, "failed"),
    (ReconCheck("sum", "x", "x", tolerance=0.01), 100.00, 100.005, "passed"),
    (ReconCheck("sum", "x", "x", tolerance=0.01), 100.00, 100.5, "failed"),
    (ReconCheck("sum", "x", "x", tolerance_percent=1.0), 100.0, 100.9, "passed"),
    (ReconCheck("max", "d", "d"), "2026-01-01", "2026-01-01", "passed"),
    (ReconCheck("max", "d", "d"), "2026-01-01", "2026-01-02", "failed"),
    (ReconCheck("sum", "x", "x"), None, None, "passed"),
])
def test_recon_compare(check, s, t, status):
    assert _compare(check, s, t).status == status


class _FakeSMTP(socketserver.StreamRequestHandler):
    """Just enough SMTP for a relay test (no TLS, no login)."""
    messages: list = []

    def handle(self):
        self.wfile.write(b"220 fake\r\n")
        data = False
        buf = []
        for raw in self.rfile:
            line = raw.decode().rstrip("\r\n")
            if data:
                if line == ".":
                    data = False
                    _FakeSMTP.messages.append("\n".join(buf))
                    self.wfile.write(b"250 ok\r\n")
                else:
                    buf.append(line)
                continue
            cmd = line.split(" ")[0].upper()
            if cmd in ("EHLO", "HELO"):
                self.wfile.write(b"250 fake\r\n")
            elif cmd == "DATA":
                data = True
                self.wfile.write(b"354 go\r\n")
            elif cmd == "QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


def test_smtp_relay_without_password():
    server = socketserver.TCPServer(("127.0.0.1", 0), _FakeSMTP)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        mail = {"provider": "smtp-relay", "host": "127.0.0.1", "port": server.server_address[1],
                "starttls": False, "user": "ignored", "from": "alerts@acme.com"}
        out = notify.send([notify.Recipient("email", "team@acme.com", "source")], "subj", "body", {}, {"mail": mail})
        assert out[0].status == "sent", out[0].error
        assert "Subject: subj" in _FakeSMTP.messages[-1] and "alerts@acme.com" in _FakeSMTP.messages[-1]
    finally:
        server.shutdown()
        server.server_close()


def test_microsoft365_graph_without_password(webhook, monkeypatch):
    monkeypatch.setattr(notify, "_graph_token", lambda mail: "token-from-managed-identity")
    mail = {"provider": "microsoft365", "from": "alerts@acme.com", "graph_url": webhook.url}
    out = notify.send([notify.Recipient("email", "team@acme.com", "source")], "subj", "body", {}, {"mail": mail})
    assert out[0].status == "sent", out[0].error
    call = webhook.calls[0]
    assert call["path"] == "/users/alerts@acme.com/sendMail"
    assert call["headers"]["Authorization"] == "Bearer token-from-managed-identity"
    assert call["json"]["message"]["toRecipients"][0]["emailAddress"]["address"] == "team@acme.com"


def test_aws_ses_with_iam_role(monkeypatch):
    sent = {}

    class Client:
        def send_email(self, **kw):
            sent.update(kw)

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name, region_name=None: Client()))
    mail = {"provider": "aws-ses", "from": "alerts@acme.com", "region": "eu-north-1"}
    out = notify.send([notify.Recipient("email", "team@acme.com", "source")], "subj", "body", {}, {"mail": mail})
    assert out[0].status == "sent", out[0].error
    assert sent["Destination"] == {"ToAddresses": ["team@acme.com"]} and sent["FromEmailAddress"] == "alerts@acme.com"


def test_unknown_mail_provider_and_legacy_smtp_block():
    out = notify.send([notify.Recipient("email", "a@b.com", "p")], "s", "b", {}, {"mail": {"provider": "fax"}})
    assert out[0].status == "failed" and "unknown mail provider" in out[0].error
    assert notify.mail_settings({"smtp": {"host": "x"}})["provider"] == "smtp"


@pytest.fixture
def memory_keyring():
    keyring = pytest.importorskip("keyring")
    from keyring.backend import KeyringBackend

    class Memory(KeyringBackend):
        priority = 1
        store: dict = {}

        def get_password(self, service, username):
            return self.store.get((service, username))

        def set_password(self, service, username, password):
            self.store[(service, username)] = password

        def delete_password(self, service, username):
            del self.store[(service, username)]

    previous = keyring.get_keyring()
    keyring.set_keyring(Memory())
    yield keyring
    keyring.set_keyring(previous)


def test_keychain_secrets(memory_keyring, monkeypatch, capsys):
    from odcr.cli import main

    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("s3cret\n"))
    assert main(["secret", "set", "SMTP_PASSWORD", "--stdin"]) == 0
    assert interpolate("${keyring:SMTP_PASSWORD}") == "s3cret"
    assert main(["secret", "check", "SMTP_PASSWORD"]) == 0
    assert main(["secret", "delete", "SMTP_PASSWORD"]) == 0
    assert main(["secret", "check", "SMTP_PASSWORD"]) == 1
    with pytest.warns(UserWarning, match="odcr secret set SMTP_PASSWORD"):
        assert interpolate("${keyring:SMTP_PASSWORD}") == ""
