"""Notifications to the source team (from the contract's `support` channels) and the platform team (config).

Channels: Slack, Microsoft Teams (Workflows / Power Automate webhooks), email (SMTP with STARTTLS or
implicit TLS), Google Chat, Discord, PagerDuty, Opsgenie, any JSON webhook, and the console.

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


def _send_email(smtp: dict[str, Any], to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.get("from", "odcr@localhost")
    msg["To"] = to
    msg.set_content(body)
    host, timeout = smtp.get("host"), float(smtp.get("timeout", 10))
    if not host:
        raise ValueError("no mail server configured: set SMTP_HOST (and SMTP_USER / SMTP_PASSWORD) in .env, "
                         "or remove email from the notifications")
    if smtp.get("ssl"):  # implicit TLS, usually port 465
        with smtplib.SMTP_SSL(host, int(smtp.get("port", 465)), timeout=timeout,
                              context=_ssl_context(smtp)) as server:
            if smtp.get("user"):
                server.login(smtp["user"], smtp.get("password", ""))
            server.send_message(msg)
        return
    with smtplib.SMTP(host, int(smtp.get("port", 587 if smtp.get("starttls") else 25)), timeout=timeout) as server:
        if smtp.get("starttls"):
            server.starttls(context=_ssl_context(smtp))
        if smtp.get("user"):
            server.login(smtp["user"], smtp.get("password", ""))
        server.send_message(msg)


def _deliver(r: Recipient, subject: str, body: str, details: dict[str, Any], settings: dict[str, Any]) -> None:
    status = str(details.get("status", "fail"))
    if r.channel == "console":
        print(f"{subject}\n{body}")
    elif r.channel == "email":
        _send_email(settings.get("smtp") or {}, r.target, subject, body)
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
    """Send to every recipient. `settings` is the config's `notifications` block (smtp, ca_bundle, proxy)."""
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
