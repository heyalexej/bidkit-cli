"""Binary Accept negotiation, unknown-header wire routing, and override-table hygiene."""

from __future__ import annotations

import io
import json
import stat
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from bidkit import EbayClient, EbayConfig

from bidkit_cli import manifest as manifest_mod
from bidkit_cli.commands import auth as auth_module
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ConfigError, SafetyError, UsageError, ValidationError_
from bidkit_cli.manifest import Manifest
from bidkit_cli.safety import effective_risk, validate_overrides


def _ctx(manifest: Manifest, handler, **config) -> CliContext:
    client = EbayClient(
        EbayConfig(access_token="t", **config),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    return ctx


def _run(ctx, op, **call) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, **call)
    return buf.getvalue()


# --- F2: binary responses negotiate the right media type -------------------

def test_f2_injects_accept_for_binary_feed_download(manifest: Manifest) -> None:
    """Feed file ops have no Accept param; the CLI must inject octet-stream."""
    op = manifest.get("sell_feed.getInputFile")
    assert op.success_response.kind == "bytes"

    ctx = _ctx(manifest, lambda req: httpx.Response(200, content=b"\0PNG"))
    ctx.dry_run = True
    preview = json.loads(_run(
        ctx, op, path_params={"task_id": "T1"}, query_params={},
        header_params={}, body=None, files={},
    ))
    assert preview["headers"]["Accept"] == "application/octet-stream"


def test_f2_accept_reaches_the_wire(manifest: Manifest, tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"\0PNG")

    ctx = _ctx(manifest, handler)
    ctx.output_file = str(tmp_path / "out.bin")
    ctx.force = True
    op = manifest.get("sell_feed.getInputFile")
    _run(
        ctx, op, path_params={"task_id": "T1"}, query_params={},
        header_params={}, body=None, files={},
    )
    assert seen[0].headers["accept"] == "application/octet-stream"


def test_f2_label_download_defaults_accept_application_pdf(manifest: Manifest) -> None:
    """downloadLabelFile declares its own Accept param; a default still applies."""
    ctx = _ctx(manifest, lambda req: httpx.Response(200, content=b"%PDF"))
    ctx.dry_run = True
    op = manifest.get("sell_logistics.downloadLabelFile")
    preview = json.loads(_run(
        ctx, op, path_params={"shipmentId": "S1"}, query_params={},
        header_params={}, body=None, files={},
    ))
    assert preview["headers"]["Accept"] == "application/pdf"


def test_f2_user_supplied_accept_is_respected(manifest: Manifest) -> None:
    ctx = _ctx(manifest, lambda req: httpx.Response(200, content=b"x"))
    ctx.dry_run = True
    op = manifest.get("sell_feed.getInputFile")
    preview = json.loads(_run(
        ctx, op, path_params={"task_id": "T1"}, query_params={},
        header_params={"Accept": "application/x-custom"}, body=None, files={},
    ))
    assert preview["headers"]["Accept"] == "application/x-custom"


# --- F7: unknown headers are not silently dropped --------------------------

def test_f7_unknown_header_reaches_wire_when_allowed(manifest: Manifest) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    ctx = _ctx(manifest, handler)
    op = manifest.get("sell_inventory.getInventoryItem")
    # The allow-unknown gate lives in the parsing layer; dispatch receives an
    # already-collected unknown header and must route it through transport.
    _run(
        ctx, op, path_params={"sku": "A"}, query_params={},
        header_params={"X-Debug-Hint": "trace-me"}, body=None, files={},
    )
    assert seen[0].headers["x-debug-hint"] == "trace-me"


# --- F4: dry-run validates inputs before preview ---------------------------

def test_f4_dry_run_rejects_invalid_model_body(manifest: Manifest) -> None:
    """A malformed body is rejected during dry-run, before any network/token."""
    network_called = []

    def handler(request: httpx.Request) -> httpx.Response:
        network_called.append(request)
        return httpx.Response(200, json={})

    ctx = _ctx(manifest, handler)
    ctx.dry_run = True
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    with pytest.raises(ValidationError_):
        execute(
            ctx, op, path_params={"sku": "X"}, query_params={},
            header_params={}, body={"product": "not-an-object"}, files={},
        )
    assert network_called == []  # never sent


def test_f4_dry_run_rejects_missing_required_binary(manifest: Manifest) -> None:
    ctx = _ctx(manifest, lambda req: httpx.Response(200))
    ctx.dry_run = True
    op = manifest.get("commerce_media.uploadVideo")
    with pytest.raises(UsageError):
        execute(ctx, op, path_params={}, query_params={}, header_params={}, body=None, files={})


def test_f4_dry_run_rejects_missing_required_multipart_file(manifest: Manifest) -> None:
    ctx = _ctx(manifest, lambda req: httpx.Response(200))
    ctx.dry_run = True
    op = manifest.get("commerce_media.createImageFromFile")
    with pytest.raises(UsageError):
        execute(ctx, op, path_params={}, query_params={}, header_params={}, body=None, files={})


# --- F3: override table parity ---------------------------------------------

def test_f3_override_table_has_no_stale_or_redundant_entries(manifest: Manifest) -> None:
    assert validate_overrides(manifest) == []


def test_f3_find_listing_recommendations_is_read(manifest: Manifest) -> None:
    op = manifest.get("sell_recommendation.findListingRecommendations")
    assert op.risk == "unknown"
    risk, reason = effective_risk(op)
    assert risk == "read"
    assert reason


def test_f3_test_subscription_stays_blocked_with_reason(manifest: Manifest) -> None:
    op = manifest.get("commerce_notification.testSubscription")
    risk, reason = effective_risk(op)
    assert risk == "unknown"
    assert reason and "notification" in reason.lower()
    # The classifier refuses even with --allow-write --yes (external side
    # effects are not overridable with --allow-write-expert either), so the call
    # cannot leave the process as a "read".
    from bidkit_cli.safety import classify_safety

    with pytest.raises(SafetyError):
        classify_safety(op, allow_write=True, allow_write_expert=True, yes=True)


def test_f3_stale_ids_are_gone_from_the_table() -> None:
    from bidkit_cli.safety import _OVERRIDES

    keys = {o.operation_key for o in _OVERRIDES}
    # Stale operation ids must no longer be present in the override table.
    assert "buy_marketplace_insights.search" not in keys
    assert "commerce_notification.test" not in keys
    assert "sell_recommendation.getListingRecommendations" not in keys
    # Redundant GETs must not be listed.
    assert "sell_marketing.getReport" not in keys
    assert "sell_compliance.getListingViolations" not in keys


# --- F5: SDK compatibility validation --------------------------------------

def test_f5_current_install_is_compatible(manifest: Manifest) -> None:
    manifest_mod.assert_sdk_compatible(manifest)  # must not raise


def test_f5_mismatched_generation_is_rejected(monkeypatch, manifest: Manifest) -> None:
    monkeypatch.setattr(manifest_mod, "_installed_sdk_version", lambda: "0.2.0")
    with pytest.raises(ConfigError):
        manifest_mod.assert_sdk_compatible(manifest)


def test_f5_patch_release_is_accepted(monkeypatch, manifest: Manifest) -> None:
    monkeypatch.setattr(manifest_mod, "_installed_sdk_version", lambda: "0.1.9")
    manifest_mod.assert_sdk_compatible(manifest)  # same 0.1.x series


# --- F6: credential file permissions ---------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_f6_written_config_file_is_mode_0600(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "config.json"
    tokens = SimpleNamespace(
        refresh_token="r",
        access_token="a",
        token_expiry=__import__("datetime").datetime.now(__import__("datetime").UTC),
        refresh_token_expiry=None,
    )
    auth_module._write_tokens(target, tokens)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    # round-trip: the written JSON is valid and carries the refresh token.
    data = json.loads(target.read_text())
    assert data["credentials"]["refresh_token"] == "r"


# --- F11: describe shows effective risk ------------------------------------

def test_f11_describe_shows_effective_risk(manifest: Manifest) -> None:
    from click.testing import CliRunner

    from bidkit_cli.app import cli

    result = CliRunner().invoke(cli, ["api", "describe", "buy_browse.searchByImage"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["risk"] == "unknown"  # base
    assert payload["effective_risk"]["risk"] == "read"
    assert payload["effective_risk"]["base_risk"] == "unknown"
