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
_FILE = re.compile(r"\$\{file:([^}]+)\}")
_KEYRING = re.compile(r"\$\{keyring:([^}]+)\}")
KEYRING_SERVICE = "odcr"


def keyring_get(name: str) -> str:
    """A secret from the OS keychain (macOS Keychain, Windows Credential Manager, Secret Service on Linux)."""
    import warnings

    try:
        import keyring
    except ImportError:
        warnings.warn(f"${{keyring:{name}}} needs: pip install 'odcr[keyring]'", stacklevel=2)
        return ""
    value = keyring.get_password(KEYRING_SERVICE, name)
    if value is None:  # not fatal: only the connection or channel that uses it will fail
        warnings.warn(f"secret '{name}' is not in the OS keychain; store it with: odcr secret set {name}",
                      stacklevel=2)
        return ""
    return value


class ConfigError(ValueError):
    pass


def interpolate(value: Any) -> Any:
    """Resolve ${VAR}, ${VAR:-default}, ${file:/path/to/secret} (Docker / Kubernetes secrets) and
    ${keyring:NAME} (the OS keychain; store with `odcr secret set NAME`)."""
    if isinstance(value, str):
        value = _FILE.sub(lambda m: Path(os.path.expanduser(m.group(1))).read_text(encoding="utf-8").strip(), value)
        value = _KEYRING.sub(lambda m: keyring_get(m.group(1).strip()), value)
        def sub(m: re.Match[str]) -> str:
            name, default = m.group(1), m.group(2)
            value = os.environ.get(name)
            if default is not None:  # ${VAR:-default}: like the shell, an empty value also uses the default
                return value if value else default
            return value or ""
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
    meta_connection: str | None = None  # store meta tables on another connection (e.g. for read-only sources)
    contracts: dict[str, Any] = field(default_factory=lambda: {"path": "contracts"})
    base_dir: Path = field(default_factory=Path.cwd)

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


def parse_config(doc: dict[str, Any] | None, base_dir: Path | None = None) -> Config:
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
    contracts = doc.get("contracts") or {"path": "contracts"}
    if isinstance(contracts, str):
        contracts = {"path": contracts}
    if meta.get("connection") and meta["connection"] not in conns:
        raise ConfigError(f"meta.connection '{meta['connection']}' is not a defined connection")
    return Config(
        connections=conns,
        meta_schema=str(meta.get("schema", DEFAULT_META_SCHEMA)),
        notifications=doc.get("notifications") or {},
        on_fail=str(doc.get("on_fail", "quarantine")),
        meta_connection=meta.get("connection"),
        contracts=contracts,
        base_dir=base_dir or Path.cwd(),
    )


def load_dotenv(path: Path) -> None:
    """Load KEY=value lines from a .env file into the environment (existing variables win)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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
    load_dotenv(p.resolve().parent / ".env")
    return parse_config(yaml.safe_load(p.read_text(encoding="utf-8")), base_dir=p.resolve().parent)
