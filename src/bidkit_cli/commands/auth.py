"""``bidkit auth`` — configuration and OAuth diagnostics (spec §13).

doctor is read-only and never hits the network unless --check-network is set.
login reuses the SDK authorization-code flow with the existing config format.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

import click

from ..config import keyset_env, resolve_config_path
from ..context import CliContext
from ..errors import ConfigError
from ..rendering import emit_json

REDACT_LEN = 8


@click.group("auth", help="Authenticate and inspect OAuth configuration.")
def auth_group() -> None:
    pass


@auth_group.command("doctor")
@click.option("--check-network", is_flag=True, default=False,
              help="Verify the app keyset via a client-credentials token request.")
@click.option("--check-user-token", "check_user_token", is_flag=True, default=False,
              help="Verify the configured refresh token via a read-only refresh exchange.")
@click.option("--show-capabilities", "show_capabilities", is_flag=True, default=False,
              help="Include the capability policy snapshot (restricted/broken surfaces).")
@click.pass_context
def auth_doctor(
    ctx: click.Context, check_network: bool, check_user_token: bool,
    show_capabilities: bool,
) -> None:
    """Read-only diagnostic of config, credentials, signing, and token cache.

    ``--check-network`` proves the application keyset can mint a *client*
    token (the client-credentials grant). It does **not** prove the configured
    refresh token or seller consent is usable — use ``--check-user-token`` for
    that. Neither check mutates account state, and no token
    value is ever printed.
    """
    context: CliContext = ctx.obj
    config = context.config
    report = _doctor_report(context, config)
    if check_network:
        report["network"] = _check_network(config)
    if check_user_token:
        report["user_token"] = _check_user_token(config)
    if show_capabilities:
        from ..commands.capabilities import capabilities_snapshot

        report["capabilities"] = capabilities_snapshot(ctx.obj)
    emit_json(report, pretty=context.pretty)


def _doctor_report(context: CliContext, config: Any) -> dict[str, Any]:
    path = resolve_config_path(context.config_path)
    signing_ok = None
    if config.signing is not None:
        try:
            _ = config.signing.private_key_value  # type: ignore[attr-defined]
            signing_ok = True
        except Exception:  # noqa: BLE001
            signing_ok = False
    token_cache_path = Path(context.token_cache_path)
    # A first-install ``ready`` verdict plus actionable ``next_steps``, so a
    # fresh agent can reach an authorized call without folklore. ``ready`` is
    # True only when the keyset, a user token, and signing are all in place.
    ready, blockers = _auth_readiness(config, signing_ok)
    return {
        "ready": ready,
        "next_steps": blockers,
        "config_path": str(path),
        "config_exists": path.exists(),
        "environment": "sandbox" if config.sandbox else "production",
        "marketplace_id": config.marketplace_id,
        "app_id": _redact(config.app_id),
        "cert_id": _present(config.cert_id),
        "ru_name": _present(config.ru_name),
        "refresh_token": _present(config.refresh_token),
        "access_token": _present(config.access_token),
        "scopes": list(config.scopes),
        "sandbox_keyset_mismatch": _keyset_mismatch(config),
        "signing": {
            "configured": config.signing is not None,
            "parseable": signing_ok,
        },
        "token_cache": {
            "path": str(token_cache_path),
            "exists": token_cache_path.exists(),
        },
        "sdk_version": _safe_version("bidkit"),
        "cli_version": _safe_version("bidkit-cli"),
    }


def _auth_readiness(config: Any, signing_ok: bool | None) -> tuple[bool, list[str]]:
    """First-install readiness + actionable next steps.

    Returns ``(ready, next_steps)``. An agent with no config gets a precise list
    of what to create and where, instead of a raw field dump with no verdict.
    The ``auth init`` skeleton's placeholder values count as *unconfigured*:
    without that, an untouched skeleton reads as a healthy keyset and the next
    step steers straight to ``auth login``, which would send the user to eBay
    with a garbage client id.
    """
    blockers: list[str] = []
    keyset = (config.app_id, config.cert_id, config.ru_name)
    if not all(keyset) or any(_is_placeholder(v) for v in keyset):
        blockers.append(
            "Create the config file with the application keyset "
            "(app_id, cert_id, ru_name) from "
            "https://developer.ebay.com/my/keys, then run `bidkit auth login`."
        )
    if not config.refresh_token and not config.access_token:
        blockers.append(
            "No user token yet: run `bidkit auth login` to mint a refresh token "
            "via the authorization-code flow."
        )
    if signing_ok is False:
        blockers.append(
            "A signing key is configured but not parseable; check the keyset "
            "or remove the signing block for non-signing surfaces."
        )
    return (not blockers), blockers


def _is_placeholder(value: Any) -> bool:
    """True for the ``auth init`` skeleton values that must be replaced."""
    return isinstance(value, str) and value.startswith("REPLACE_WITH_")


def _safe_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001
        return "unknown"


def _present(value: Any) -> str:
    # Report the *actual* set/missing status. The previous
    # ``<set:{REDACT_LEN} chars>`` leaked REDACT_LEN into an f-string and read
    # as "the value is 8 characters", which is false for every credential.
    return "<set>" if value else "<missing>"


def _redact(value: Any) -> str:
    if not value:
        return "<missing>"
    text = str(value)
    return f"{text[:4]}…{text[-2:]}" if len(text) > 8 else "<short>"


def _keyset_mismatch(config: Any) -> bool:
    env = keyset_env(config.app_id)
    if env is None:
        return False
    return (env == "sandbox") != config.sandbox


def _check_network(config: Any) -> dict[str, Any]:
    """Verify the app keyset with a client-credentials grant.

    The client-credentials grant only accepts the public application scope; any
    user-only scope in the configured set makes eBay return ``invalid_scope``
    even though the keyset is healthy. We force the application scope (and clear
    the refresh token so the SDK takes the client path) so this check validates
    the keyset independently of seller consent.
    """

    from bidkit import EbayClient, FileTokenCache

    from ..locales import CLIENT_CREDENTIALS_SCOPE

    try:
        # Scope to the public application grant and drop the refresh token so
        # access_token() takes the client path regardless of user config.
        client = EbayClient(
            config.model_copy(
                update={
                    "refresh_token": None,
                    "scopes": (CLIENT_CREDENTIALS_SCOPE,),
                }
            ),
            token_cache=FileTokenCache(),
        )
        try:
            client.auth.access_token(client.http)
            return {
                "ok": True,
                "token_type": "client_credentials",
                "scope": CLIENT_CREDENTIALS_SCOPE,
            }
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "token_type": "client_credentials",
            "scope": CLIENT_CREDENTIALS_SCOPE,
            "error": str(exc),
        }


def _check_user_token(config: Any) -> dict[str, Any]:
    """Verify the configured refresh token via a read-only refresh exchange.

    This is the check ``--check-network`` cannot make: it proves the stored
    refresh token is still valid and the seller/user scopes are usable, without
    mutating account state. Only the result is returned — never the tokens.
    """

    from bidkit import EbayClient, FileTokenCache

    if not config.refresh_token:
        return {
            "ok": False,
            "token_type": "user",
            "grant": "refresh_token",
            "error": "no refresh_token configured",
        }
    try:
        # access_token() refreshes the user token when a refresh_token is set.
        client = EbayClient(config, token_cache=FileTokenCache())
        try:
            client.auth.access_token(client.http)
            return {"ok": True, "token_type": "user", "grant": "refresh_token"}
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "token_type": "user", "grant": "refresh_token", "error": str(exc)}


@auth_group.command("login")
@click.option("--no-browser", is_flag=True, default=False, help="Print the URL only.")
@click.option("--redirect-url", default=None, help="The full post-consent redirect URL.")
@click.option("--code", default=None, help="The authorization code itself.")
@click.option("--scopes", default=None, help="Space-separated scope list.")
@click.option("--write-config", is_flag=True, default=False,
              help="Persist tokens + expiries back into the config file.")
@click.pass_context
def auth_login(
    ctx: click.Context,
    no_browser: bool,
    redirect_url: str | None,
    code: str | None,
    scopes: str | None,
    write_config: bool,
) -> None:
    """Mint an eBay user refresh token via the authorization-code flow.

    Reuses the SDK's ``EbayClient.exchange_code``; preserves the existing
    bidkit-cli config format. Sandbox/production keyset mismatch is detected
    before any browser opens.
    """

    from bidkit import EbayClient
    from bidkit.errors import EbayAuthError, EbayConfigError

    context: CliContext = ctx.obj
    config = context.config
    if scopes:
        config = config.model_copy(update={"scopes": tuple(s for s in scopes.split() if s)})
    # --marketplace is a global option (hoisted by the argv
    # reorderer), so read it from the resolved context instead of a dead local
    # declaration that could never receive the value.
    if context.marketplace:
        config = config.model_copy(update={"marketplace_id": context.marketplace})

    if any(_is_placeholder(v) for v in (config.app_id, config.cert_id, config.ru_name)):
        raise ConfigError(
            "the config file still contains the `auth init` placeholder keyset",
            hint=(
                "Edit the config file and replace the REPLACE_WITH_… values with "
                "your application keyset from https://developer.ebay.com/my/keys, "
                "then re-run `bidkit auth login`."
            ),
        )
    env = keyset_env(config.app_id)
    if env == "production" and config.sandbox:
        raise ConfigError(
            f"App ID '{config.app_id}' is a PRODUCTION (-PRD-) keyset but environment is sandbox."
        )
    if env == "sandbox" and not config.sandbox:
        raise ConfigError(
            f"App ID '{config.app_id}' is a SANDBOX (-SBX-) keyset; set --environment sandbox."
        )

    import bidkit

    client = EbayClient(
        config, token_cache=bidkit.FileTokenCache(context.token_cache_path)
    )
    try:
        if code or redirect_url:
            resolved = code or _extract_code(redirect_url or "")
        else:
            try:
                url = client.authorization_url(state="cli")
            except EbayConfigError as exc:
                # A fresh install hits this when the keyset is
                # not configured. Give an actionable hint pointing at the config
                # path and where the credentials come from, instead of a bare msg.
                raise ConfigError(
                    str(exc),
                    hint=(
                        "bidkit needs an application keyset (app_id, cert_id, "
                        "ru_name) to build the authorization URL. Create the "
                        "config file at "
                        f"{resolve_config_path(context.config_path)} "
                        "with credentials from "
                        "https://developer.ebay.com/my/keys, then re-run "
                        "`bidkit auth login`."
                    ),
                ) from exc
            click.echo(f"\n1) Grant consent in your browser:\n   {url}\n")
            if not no_browser:
                webbrowser.open(url)
            click.echo("2) After consent, paste the redirect URL or code here:")
            try:
                pasted = input("   > ").strip()
            except EOFError:
                raise ConfigError("no input received") from None
            resolved = _extract_code(pasted)
        try:
            tokens = client.exchange_code(resolved)
        except EbayAuthError as exc:
            raise ConfigError(f"exchange failed: {exc}") from exc
    finally:
        client.close()

    summary = {
        "refresh_token": _present(tokens.refresh_token),
        "refresh_token_expiry": (
            tokens.refresh_token_expiry.isoformat()
            if tokens.refresh_token_expiry
            else None
        ),
        "access_token": _present(tokens.access_token),
        "access_token_expiry": tokens.token_expiry.isoformat(),
    }
    if write_config:
        target = resolve_config_path(context.config_path)
        _write_tokens(target, tokens)
        summary["wrote_config"] = str(target)
    emit_json(summary, pretty=context.pretty)


def _extract_code(pasted: str) -> str:
    from urllib.parse import parse_qs, unquote, urlsplit

    pasted = pasted.strip()
    if pasted.lower().startswith("http"):
        query = parse_qs(urlsplit(pasted).query)
        if "code" not in query:
            raise ConfigError("no 'code' parameter found in the pasted URL")
        return query["code"][0]
    return unquote(pasted)


def _write_tokens(path: Path, tokens: Any) -> None:
    import json
    import os

    data: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
    creds = data.setdefault("credentials", {})
    creds["refresh_token"] = tokens.refresh_token
    creds["access_token"] = tokens.access_token
    creds["access_token_expiry"] = tokens.token_expiry.isoformat()
    if tokens.refresh_token_expiry is not None:
        creds["refresh_token_expiry"] = tokens.refresh_token_expiry.isoformat()
    # Credentials persist here: create the directory 0700 and the file 0600 so
    # we never rely on the user's umask for secret permissions.
    path.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path.parent, 0o700)
    # Atomic write: temp file in the same dir, 0600, then rename.
    import tempfile

    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    _chmod_best_effort(path, 0o600)


def _chmod_best_effort(target: Path, mode: int) -> None:
    """Apply ``mode`` on POSIX; ignore on platforms without chmod."""
    import contextlib
    import os

    with contextlib.suppress(OSError):
        os.chmod(target, mode)


@auth_group.command("init")
@click.pass_context
def auth_init(ctx: click.Context) -> None:
    """Write a skeleton config so a fresh install can reach ``auth login``.

    Creates ``~/.config/bidkit/config.json`` with placeholder credentials,
    0600 permissions, and inline instructions naming where each value comes
    from. After filling in the keyset, run ``bidkit auth login`` to mint a user
    token. Never overwrites an existing file without ``--force``.

    ``--marketplace`` and ``--force`` are global options (hoisted by the argv
    reorderer) and are read from the context, not declared locally.
    """
    import json
    import os

    from ..errors import SafetyError

    context: CliContext = ctx.obj
    target = resolve_config_path(context.config_path)
    if target.exists() and not context.force:
        raise SafetyError(
            f"config already exists at {target}; pass --force to overwrite.",
            hint="bidkit auth init --force",
        )
    skeleton = {
        "credentials": {
            "app_id": "REPLACE_WITH_APP_ID_FROM_developer.ebay.com/my/keys",
            "cert_id": "REPLACE_WITH_CERT_ID",
            "ru_name": "REPLACE_WITH_RU_NAME",
        },
        "marketplace_id": context.marketplace or "EBAY_US",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(target.parent, 0o700)
    fd, tmp = _mkstemp(target)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(skeleton, indent=2) + "\n")
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    emit_json(
        {
            "created": str(target),
            "next_steps": [
                "Edit the file and fill in app_id/cert_id/ru_name from "
                "https://developer.ebay.com/my/keys.",
                "Run `bidkit auth login --write-config` to mint a user refresh token.",
                "Run `bidkit auth doctor` to verify readiness.",
            ],
        },
        pretty=context.pretty,
    )


def _mkstemp(target: Path):
    import tempfile

    return tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))


@auth_group.command("scopes")
@click.option("--operation", default=None, help="Show scopes for an operation.")
@click.pass_context
def auth_scopes(ctx: click.Context, operation: str | None) -> None:
    """Show configured scopes and, where the manifest has them, operation scopes."""
    from ..errors import UsageError

    context: CliContext = ctx.obj
    config = context.config
    payload: dict[str, Any] = {"configured_scopes": list(config.scopes)}
    if operation:
        try:
            record = context.manifest.resolve(operation)
        except Exception as exc:  # noqa: BLE001
            raise UsageError(str(exc)) from exc
        payload["operation"] = record.key
        payload["operation_scopes"] = record.auth.scopes
        payload["auth_scheme"] = record.auth.scheme
    emit_json(payload, pretty=context.pretty)


@auth_group.group("cache", help="Inspect or clear the token cache.")
def auth_cache() -> None:
    pass


@auth_cache.command("path")
@click.pass_context
def cache_path(ctx: click.Context) -> None:
    context: CliContext = ctx.obj
    click.echo(context.token_cache_path)


@auth_cache.command("clear")
@click.pass_context
def cache_clear(ctx: click.Context) -> None:
    """Clear the on-disk token cache (a local destructive action; needs --yes).

    ``--yes`` is a *global* option (hoisted to the root by the argv reorderer),
    so this command must not declare it locally — the local declaration could
    never receive the value. We read the confirmation from the global context
    instead, so ``bidkit auth cache clear --yes`` works.
    """
    from ..errors import SafetyError

    context: CliContext = ctx.obj
    if not context.yes:
        raise SafetyError(
            "clearing the token cache is destructive; pass --yes to confirm",
            hint="bidkit auth cache clear --yes",
        )
    path = Path(context.token_cache_path)
    if path.exists():
        path.unlink()
        click.echo(f"removed {path}")
    else:
        click.echo("token cache does not exist")
