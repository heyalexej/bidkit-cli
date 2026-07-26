"""``bidkit config`` — inspect effective non-secret configuration (spec §7.1)."""

from __future__ import annotations

import click

from ..context import CliContext
from ..rendering import emit_json


@click.group("config", help="Inspect effective non-secret configuration.")
def config_group() -> None:
    pass


@config_group.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Print the resolved config (secrets redacted) and precedence sources."""
    context: CliContext = ctx.obj
    config = context.config
    payload = {
        "environment": "sandbox" if config.sandbox else "production",
        "marketplace_id": config.marketplace_id,
        "accept_language": config.accept_language,
        "content_language": config.content_language,
        "app_id": _redact(config.app_id),
        "cert_id": _present(config.cert_id),
        "ru_name": _present(config.ru_name),
        "refresh_token": _present(config.refresh_token),
        "scopes": list(config.scopes),
        "signing_configured": config.signing is not None,
        "timeout": config.timeout,
        "max_retries": config.max_retries,
        "api_root": config.api_root(),
        "token_cache": context.token_cache_path,
    }
    emit_json(payload, pretty=context.pretty)


@config_group.command("locales")
@click.pass_context
def config_locales(ctx: click.Context) -> None:
    """List the marketplace → Content/Accept-Language and title-limit table.

    Use ``--marketplace EBAY_DE --marketplace-locale`` (or ``--content-language
    de-DE``) to set the locale for German listings without the unknown-header
    escape hatch.
    """
    from ..locales import locales_table

    context: CliContext = ctx.obj
    emit_json({"marketplaces": locales_table()}, pretty=context.pretty)


def _present(value: object) -> str:
    return "<set>" if value else "<missing>"


def _redact(value: object) -> str:
    if not value:
        return "<missing>"
    text = str(value)
    return f"{text[:4]}…{text[-2:]}" if len(text) > 8 else "<short>"
