"""Framework configuration (odcr.yaml) with ${ENV_VAR} and ${ENV_VAR:-default} interpolation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .meta import DEFAULT_META_SCHEMA

_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(ValueError):
    pass


def interpolate(value: Any) -> Any:
    if isinstance(value, str):
        def sub(m: re.Match[str]) -> str:
            name, default = m.group(1), m.group(2)
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            return ""
        return _ENV.sub(sub, value)
    if isinstance(value, dict):
        return {k: interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v) for v in value]
    return value


@dataclass
class Config:
    connections: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta_schema: str = DEFAULT_META_SCHEMA
    notifications: dict[str, Any] = field(default_factory=dict)
    on_fail: str = "quarantine"  # quarantine | log

    def connection(self, name: str) -> dict[str, Any]:
        if name not in self.connections:
            known = ", ".join(sorted(self.connections)) or "none"
            raise ConfigError(f"Connection '{name}' not found in config (known: {known})")
        return dict(self.connections[name])

    @property
    def notify_on(self) -> list[str]:
        return [str(s).lower() for s in self.notifications.get("notify_on", ["fail"])]

    @property
    def platform_team(self) -> list[dict[str, Any]]:
        return list(self.notifications.get("platform_team") or [])


def parse_config(doc: dict[str, Any] | None) -> Config:
    doc = interpolate(doc or {})
    if not isinstance(doc, dict):
        raise ConfigError("Config must be a YAML mapping")
    conns = doc.get("connections") or {}
    if not isinstance(conns, dict):
        raise ConfigError("connections must be a mapping of name -> settings")
    for name, c in conns.items():
        if not isinstance(c, dict) or "type" not in c:
            raise ConfigError(f"connection '{name}' needs a 'type'")
    meta = doc.get("meta") or {}
    return Config(
        connections=conns,
        meta_schema=str(meta.get("schema", DEFAULT_META_SCHEMA)),
        notifications=doc.get("notifications") or {},
        on_fail=str(doc.get("on_fail", "quarantine")),
    )


def load_config(path: str | Path | None) -> Config:
    if path is None:
        for candidate in ("odcr.yaml", "odcr.yml"):
            if Path(candidate).exists():
                path = candidate
                break
        else:
            return Config()
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")
    return parse_config(yaml.safe_load(p.read_text(encoding="utf-8")))
