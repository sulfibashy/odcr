"""Notifications to the source team (from the contract) and the platform team (from config).

Uses only the Python standard library: webhooks over HTTPS (Slack, Teams, any
JSON endpoint) and email over SMTP. A failed notification never breaks a run;
every attempt is logged in the `notifications` meta table.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from .contract import Contact

log = logging.getLogger("odcr.notify")


@dataclass
class Recipient:
    channel: str  # slack | teams | webhook | email | console
    target: str
    audience: str  # source | platform


@dataclass
class Delivery:
    recipient: Recipient
    status: str  # sent | failed
    error: str | None = None


def recipients(contacts: list[Contact], platform_team: list[dict[str, Any]]) -> list[Recipient]:
    out = [Recipient(c.kind, c.target, "source") for c in contacts]
    for entry in platform_team:
        kind = str(entry.get("type", "webhook")).lower()
        if kind == "email":
            to = entry.get("to") or []
            for addr in [to] if isinstance(to, str) else to:
                if addr:
                    out.append(Recipient("email", str(addr), "platform"))
        elif kind == "console":
            out.append(Recipient("console", "stdout", "platform"))
        elif entry.get("url"):
            out.append(Recipient(kind, str(entry["url"]), "platform"))
    return out


def _post_json(url: str, payload: dict[str, Any], timeout: float = 10.0) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL comes from config/contract
        if resp.status >= 300:
            raise RuntimeError(f"HTTP {resp.status}")


def _payload(channel: str, subject: str, body: str, details: dict[str, Any]) -> dict[str, Any]:
    if channel == "teams":
        return {"title": subject, "text": body.replace("\n", "  \n")}
    if channel == "slack":
        return {"text": f"*{subject}*\n{body}"}
    return {"subject": subject, "text": body, "details": details}


def _send_email(smtp: dict[str, Any], to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.get("from", "odcr@localhost")
    msg["To"] = to
    msg.set_content(body)
    host, port = smtp.get("host", "localhost"), int(smtp.get("port", 25))
    with smtplib.SMTP(host, port, timeout=10) as server:
        if smtp.get("starttls"):
            server.starttls()
        if smtp.get("user"):
            server.login(smtp["user"], smtp.get("password", ""))
        server.send_message(msg)


def send(recips: list[Recipient], subject: str, body: str, details: dict[str, Any],
         smtp: dict[str, Any] | None = None) -> list[Delivery]:
    results: list[Delivery] = []
    for r in recips:
        try:
            if r.channel == "console":
                print(f"{subject}\n{body}")
            elif r.channel == "email":
                _send_email(smtp or {}, r.target, subject, body)
            elif r.channel in ("slack", "teams", "webhook"):
                _post_json(r.target, _payload(r.channel, subject, body, details))
            else:
                raise ValueError(f"unknown channel {r.channel}")
            results.append(Delivery(r, "sent"))
        except Exception as exc:  # noqa: BLE001 - notifications must never break the run
            log.warning("Notification to %s (%s) failed: %s", r.target, r.channel, exc)
            results.append(Delivery(r, "failed", str(exc)))
    return results


def mask(target: str) -> str:
    """Hide webhook secrets when logging a recipient."""
    if target.startswith("http"):
        head = target.split("//", 1)[-1].split("/", 1)[0]
        return f"{target.split('//')[0]}//{head}/***"
    return target
