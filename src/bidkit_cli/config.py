"""Effective configuration resolution (spec §8.1).

Precedence, highest first:
  1. command-line overrides (--environment, --marketplace, --timeout, ...);
  2. EBAY_* environment variables;
  3. the config file selected by --config (bidkit-cli JSON format);
  4. bidkit defaults.

The config file lives at ``~/.config/bidkit/config.json``. A file at the older
``~/.config/ebay-cli/config.json`` location (same JSON layout, from this tool's
predecessor) is read as a silent fallback so existing setups keep working — but
everything the CLI creates or documents uses the bidkit path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bidkit import EbayConfig

from .errors import ConfigError

DEFAULT_CONFIG_PATH = "~/.config/bidkit/config.json"
LEGACY_CONFIG_PATH = "~/.config/ebay-cli/config.json"


def resolve_config_path(config_path: str | None) -> Path:
    """The config file to use: explicit > default > legacy fallback.

    An explicit ``--config`` always wins. Otherwise the bidkit path is used when
    it exists; if only the legacy predecessor file exists, that one is read (and
    ``auth login --write-config`` will keep updating it, so credentials stay in
    one file). When neither exists, the bidkit path is returned so anything that
    *creates* a config (``auth init``) creates it at the modern location.
    """
    if config_path:
        return Path(config_path).expanduser()
    default = Path(DEFAULT_CONFIG_PATH).expanduser()
    if default.exists():
        return default
    legacy = Path(LEGACY_CONFIG_PATH).expanduser()
    if legacy.exists():
        return legacy
    return default


def load_effective_config(
    *,
    config_path: str | None,
    environment: str | None,
    marketplace: str | None,
    timeout: float | None,
    max_retries: int | None,
    content_language: str | None = None,
    accept_language: str | None = None,
    marketplace_locale: bool = False,
) -> EbayConfig:
    """Build an :class:`EbayConfig` honoring CLI > env > file > defaults."""
    # 3+4: file (if present) then defaults. from_env() already layers env over
    # defaults, and from_file layers file over defaults. We start from the file
    # (authoritative for credentials), then apply env-derived fields, then CLI.
    path = resolve_config_path(config_path)

    config: EbayConfig
    if path.exists():
        try:
            config = EbayConfig.from_file(path)
        except Exception as exc:  # noqa: BLE001 - surface as a config error
            raise ConfigError(f"could not read config file {path}: {exc}") from exc
    else:
        # No file: fall back to environment, then defaults.
        config = EbayConfig.from_env()
        # If there was no file at all, also honor EBAY_ credentials that from_env
        # already captured. Re-derive from env so env-only setups work fully.
        pass

    # 2: environment variables win over file values for the fields they set.
    config = _layer_env(config)

    # 1: explicit CLI overrides win last.
    overrides: dict[str, Any] = {}
    if environment is not None:
        overrides["sandbox"] = environment == "sandbox"
    if marketplace is not None:
        overrides["marketplace_id"] = marketplace
    if timeout is not None:
        overrides["timeout"] = timeout
    if max_retries is not None:
        overrides["max_retries"] = max_retries
    # Resolve Content-Language/Accept-Language so an EBAY_DE workflow works
    # without the unknown-header escape hatch. Precedence: explicit CLI flags >
    # --marketplace-locale derivation > config file values (the SDK default is
    # en-US, so we only override when a value was actually resolved).
    from .locales import derive_languages

    resolved_content, resolved_accept = derive_languages(
        marketplace_id=marketplace or config.marketplace_id,
        marketplace_locale=marketplace_locale,
        content_language=content_language,
        accept_language=accept_language,
        config_content_language=config.content_language,
        config_accept_language=config.accept_language,
    )
    if resolved_content is not None:
        overrides["content_language"] = resolved_content
    if resolved_accept is not None:
        overrides["accept_language"] = resolved_accept
    if overrides:
        config = config.model_copy(update=overrides)
    return config


def _layer_env(config: EbayConfig) -> EbayConfig:
    """Apply EBAY_* variables on top of the file-derived config.

    EbayConfig.from_env() reads env, but we want file+env merged. We rebuild env
    values and only override the ones the environment actually set.
    """
    import os

    def value(name: str) -> str | None:
        raw = os.getenv("EBAY_" + name)
        return raw if raw not in (None, "") else None

    updates: dict[str, Any] = {}
    if (sandbox := value("SANDBOX")) is not None:
        updates["sandbox"] = sandbox.strip().lower() in {"1", "true", "yes", "on"}
    if (marketplace := value("MARKETPLACE_ID")) is not None:
        updates["marketplace_id"] = marketplace
    if (app_id := value("APP_ID")) is not None:
        updates["app_id"] = app_id
    if (cert_id := value("CERT_ID")) is not None:
        updates["cert_id"] = cert_id
    if (ru_name := value("RU_NAME")) is not None:
        updates["ru_name"] = ru_name
    if (refresh := value("REFRESH_TOKEN")) is not None:
        updates["refresh_token"] = refresh
    if (access := value("ACCESS_TOKEN")) is not None:
        updates["access_token"] = access
    if (scopes := value("SCOPES")) is not None:
        updates["scopes"] = tuple(s for s in scopes.split() if s)
    if (base := value("BASE_URL")) is not None:
        updates["base_url_override"] = base
    if updates:
        return config.model_copy(update=updates)
    return config


def keyset_env(app_id: str | None) -> str | None:
    """eBay App IDs encode the environment: ``...-PRD-...`` / ``...-SBX-...``."""
    if not app_id:
        return None
    parts = app_id.split("-")
    if "SBX" in parts:
        return "sandbox"
    if "PRD" in parts:
        return "production"
    return None
