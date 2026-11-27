"""Notifications to the source team (from the contract's `support` channels) and the platform team (config).

Channels: Slack, Microsoft Teams (Workflows / Power Automate webhooks), email, Google Chat, Discord,
PagerDuty, Opsgenie, any JSON webhook, and the console.

Email providers (`notifications.mail.provider`), most of them without any stored password:
  smtp-relay    company mail relay that trusts the server (no login)
  smtp          SMTP login; password from the OS keychain (${keyring:...}), a secret file or the environment
  microsoft365  Microsoft Graph sendMail with Entra ID: managed identity, workload identity, az login (no password)
  aws-ses       Amazon SES with the IAM role / SSO profile of the machine (no password)

Only the Python standard library is used. TLS certificates are always verified; a custom CA bundle
(corporate proxy / private CA) can be set with `ca_bundle`, and an HTTP(S) proxy with `proxy`.
A failed notification never breaks a run; every attempt is logged in the `notifications` meta table.
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from .contract import Contact

log = logging.getLogger("odcr.notify")

CHANNELS = ("slack", "teams", "email", "googlechat", "discord", "pagerduty", "opsgenie", "webhook", "console")
_ALIASES = {"msteams": "teams", "microsoft teams": "teams", "mail": "email", "smtp": "email",
            "google_chat": "googlechat", "google-chat": "googlechat", "gchat": "googlechat", "http": "webhook"}


def channel_name(tool: str) -> str:
    t = str(tool).strip().lower()
    return _ALIASES.get(t, t)


@dataclass
class Recipient:
    channel: str
    target: str  # webhook URL, email address, or integration key (PagerDuty / Opsgenie)
    audience: str  # source | platform


@dataclass
class Delivery:
    recipient: Recipient
    status: str  # sent | failed
    error: str | None = None


def recipients(contacts: list[Contact], platform_team: list[dict[str, Any]]) -> list[Recipient]:
    out = [Recipient(channel_name(c.kind), c.target, "source") for c in contacts]
    for entry in platform_team:
        kind = channel_name(entry.get("type", "webhook"))
        if kind == "email":
            to = entry.get("to") or []
            for addr in [to] if isinstance(to, str) else to:
                if addr:
                    out.append(Recipient("email", str(addr), "platform"))
        elif kind == "console":
            out.append(Recipient("console", "stdout", "platform"))
        else:
            target = entry.get("url") or entry.get("key") or entry.get("routing_key")
            if target:
                out.append(Recipient(kind, str(target), "platform"))
    return out


def _ssl_context(settings: dict[str, Any]) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=settings.get("ca_bundle") or None)
    if settings.get("verify") is False:  # strongly discouraged; only for isolated test environments
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _post_json(url: str, payload: dict[str, Any], settings: dict[str, Any],
               headers: dict[str, str] | None = None) -> None:
    data = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    handlers: list[Any] = []
    if url.startswith("https://"):
        handlers.append(urllib.request.HTTPSHandler(context=_ssl_context(settings)))
    if settings.get("proxy"):
        handlers.append(urllib.request.ProxyHandler({"http": settings["proxy"], "https": settings["proxy"]}))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=float(settings.get("timeout", 10))) as resp:  # noqa: S310 - configured URL
        if resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status}")


def mail_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """The `mail` block; the older `smtp` block still works and means provider smtp."""
    if settings.get("mail"):
        return dict(settings["mail"])
    smtp = dict(settings.get("smtp") or {})
    smtp.setdefault("provider", "smtp")
    return smtp


def _send_email(mail: dict[str, Any], to: str, subject: str, body: str, settings: dict[str, Any]) -> None:
    provider = str(mail.get("provider", "smtp")).lower()
    sender = mail.get("from") or mail.get("sender") or "odcr@localhost"
    if provider in ("smtp", "smtp-relay", "gmail"):
        _send_smtp(mail, sender, to, subject, body)
    elif provider in ("microsoft365", "graph", "office365"):
        _send_graph(mail, sender, to, subject, body, settings)
    elif provider in ("aws-ses", "ses"):
        _send_ses(mail, sender, to, subject, body)
    else:
        raise ValueError(f"unknown mail provider '{provider}' (smtp-relay, smtp, microsoft365, aws-ses)")


def _send_smtp(mail: dict[str, Any], sender: str, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)
    host, timeout = mail.get("host"), float(mail.get("timeout", 10))
    if not host:
        raise ValueError("no mail server configured: set SMTP_HOST in .env (or choose another mail provider: "
                         "microsoft365, aws-ses, smtp-relay)")
    login = mail.get("user") and str(mail.get("provider")) != "smtp-relay"
    if mail.get("ssl"):  # implicit TLS, usually port 465
        with smtplib.SMTP_SSL(host, int(mail.get("port", 465)), timeout=timeout,
                              context=_ssl_context(mail)) as server:
            if login:
                server.login(mail["user"], mail.get("password", ""))
            server.send_message(msg)
        return
    starttls = mail.get("starttls", True)
    with smtplib.SMTP(host, int(mail.get("port", 587 if starttls else 25)), timeout=timeout) as server:
        if starttls:
            server.starttls(context=_ssl_context(mail))
        if login:
            server.login(mail["user"], mail.get("password", ""))
        server.send_message(msg)


def _graph_token(mail: dict[str, Any]) -> str:
    """An Entra ID token without stored passwords: managed identity, workload identity, Azure CLI login, or a
    certificate-based service principal (AZURE_CLIENT_CERTIFICATE_PATH)."""
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise ImportError("Microsoft 365 mail needs: pip install 'odcr[microsoft365]'") from exc
    kwargs = {"managed_identity_client_id": mail["client_id"]} if mail.get("client_id") else {}
    return DefaultAzureCredential(**kwargs).get_token("https://graph.microsoft.com/.default").token


def _send_graph(mail: dict[str, Any], sender: str, to: str, subject: str, body: str,
                settings: dict[str, Any]) -> None:
    url = f"{mail.get('graph_url', 'https://graph.microsoft.com/v1.0').rstrip('/')}/users/{sender}/sendMail"
    message = {"message": {"subject": subject, "body": {"contentType": "Text", "content": body},
                           "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": False}
    _post_json(url, message, {**settings, **mail}, headers={"Authorization": f"Bearer {_graph_token(mail)}"})


def _send_ses(mail: dict[str, Any], sender: str, to: str, subject: str, body: str) -> None:
    try:
        import boto3
    except ImportError as exc:
        raise ImportError("Amazon SES mail needs: pip install 'odcr[aws-ses]'") from exc
    client = boto3.client("sesv2", region_name=mail.get("region"))  # credentials: IAM role / SSO / profile
    client.send_email(FromEmailAddress=sender, Destination={"ToAddresses": [to]},
                      Content={"Simple": {"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}}})


def _deliver(r: Recipient, subject: str, body: str, details: dict[str, Any], settings: dict[str, Any]) -> None:
    status = str(details.get("status", "fail"))
    if r.channel == "console":
        print(f"{subject}\n{body}")
    elif r.channel == "email":
        _send_email(mail_settings(settings), r.target, subject, body, settings)
    elif r.channel == "slack":
        _post_json(r.target, {"text": f"*{subject}*\n```{body}```"}, settings)
    elif r.channel == "teams":
        card = {"type": "AdaptiveCard", "version": "1.4", "body": [
            {"type": "TextBlock", "text": subject, "weight": "Bolder", "wrap": True},
            {"type": "TextBlock", "text": body, "wrap": True, "fontType": "Monospace"}]}
        _post_json(r.target, {"type": "message", "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}, settings)
    elif r.channel == "googlechat":
        _post_json(r.target, {"text": f"*{subject}*\n{body}"}, settings)
    elif r.channel == "discord":
        _post_json(r.target, {"content": f"**{subject}**\n```{body[:1800]}```"}, settings)
    elif r.channel == "pagerduty":
        _post_json(settings.get("pagerduty_url", "https://events.pagerduty.com/v2/enqueue"), {
            "routing_key": r.target, "event_action": "trigger",
            "payload": {"summary": subject[:1000], "source": "odcr",
                        "severity": "warning" if status == "warn" else "error", "custom_details": details}},
            settings)
    elif r.channel == "opsgenie":
        _post_json(settings.get("opsgenie_url", "https://api.opsgenie.com/v2/alerts"),
                   {"message": subject[:130], "description": body[:15000], "source": "odcr",
                    "priority": "P3" if status == "warn" else "P2"},
                   settings, headers={"Authorization": f"GenieKey {r.target}"})
    elif r.channel == "webhook":
        _post_json(r.target, {"subject": subject, "text": body, "details": details}, settings)
    else:
        raise ValueError(f"unknown channel '{r.channel}' (use one of {', '.join(CHANNELS)})")


def send(recips: list[Recipient], subject: str, body: str, details: dict[str, Any],
         settings: dict[str, Any] | None = None) -> list[Delivery]:
    """Send to every recipient. `settings` is the config's `notifications` block (mail, ca_bundle, proxy)."""
    settings = settings or {}
    results: list[Delivery] = []
    for r in recips:
        try:
            _deliver(r, subject, body, details, settings)
            results.append(Delivery(r, "sent"))
        except Exception as exc:  # noqa: BLE001 - notifications must never break the run
            log.warning("Notification via %s to %s failed: %s", r.channel, mask(r.target), exc)
            results.append(Delivery(r, "failed", str(exc)))
    return results


def mask(target: str) -> str:
    """Hide secrets (webhook tokens, integration keys) when logging a recipient."""
    if target.startswith("http"):
        head = target.split("//", 1)[-1].split("/", 1)[0]
        return f"{target.split('//')[0]}//{head}/***"
    if "@" in target:
        return target
    return (target[:4] + "***") if len(target) > 8 else "***"
