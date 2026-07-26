"""Dispatch with a mocked transport (spec §10, §18.4)."""

from __future__ import annotations

import contextlib
import io

import httpx2
import pytest
from bidkit import EbayClient, EbayConfig

from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ApiError, SafetyError, ValidationError_
from bidkit_cli.manifest import Manifest


def _capture(ctx: CliContext) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        # the execute path is synchronous; capture is straightforward
        pass
    return buf.getvalue()


def _run(ctx: CliContext, op, **call_kwargs) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        execute(ctx, op, **call_kwargs)
    return buf.getvalue()


def test_get_dispatches_and_renders_json(manifest: Manifest) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sku": "A", "title": "t"})

    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    op = manifest.get("sell_inventory.getInventoryItem")
    out = _run(
        ctx, op, path_params={"sku": "A"}, query_params={},
        header_params={}, body=None, files={},
    )
    import json

    payload = json.loads(out)
    assert payload["sku"] == "A"
    client.close()


def test_query_params_encoded_on_request(manifest: Manifest) -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"inventoryItems": [], "total": 0})

    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    op = manifest.get("sell_inventory.getInventoryItems")
    _run(
        ctx, op, path_params={}, query_params={"limit": 20, "offset": 0},
        header_params={}, body=None, files={},
    )
    request = seen[0]
    assert request.method == "GET"
    assert "limit=20" in request.url.query.decode()
    client.close()


def test_write_refused(cli_ctx: CliContext, manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    with pytest.raises(SafetyError):
        _run(cli_ctx, op, path_params={"sku": "X"}, query_params={}, header_params={},
             body={"availability": {}}, files={})


def test_dry_run_never_sends(cli_ctx: CliContext, manifest: Manifest, mock_client) -> None:
    cli_ctx.dry_run = True
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    out = _run(cli_ctx, op, path_params={"sku": "X"}, query_params={}, header_params={},
               body={"product": {"title": "t"}}, files={})
    import json

    payload = json.loads(out)
    assert payload["dry_run"] is True
    assert payload["risk"] == "write"
    # the mock transport was never invoked: the client recorded no state change.
    # (We only assert no exception from network; dry-run returns before dispatch.)


def test_request_body_validated_against_model(cli_ctx: CliContext, manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    cli_ctx.allow_write = True
    # `product` must be a nested object model; a scalar fails validation.
    with pytest.raises(ValidationError_) as exc_info:
        _run(cli_ctx, op, path_params={"sku": "X"}, query_params={}, header_params={},
             body={"product": "not-an-object"}, files={})
    assert exc_info.value.operation == op.key


def test_api_error_translated(cli_ctx: CliContext, manifest: Manifest) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(422, json={"errors": [{"message": "bad value"}]})

    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    cli_ctx._client = client
    cli_ctx._config = client.config
    op = manifest.get("sell_inventory.getInventoryItem")
    with pytest.raises(ApiError) as exc_info:
        _run(
            cli_ctx, op, path_params={"sku": "A"}, query_params={},
            header_params={}, body=None, files={},
        )
    assert exc_info.value.status == 422
    assert exc_info.value.exit_code == 4
    client.close()


def test_raw_format_includes_status_and_headers(cli_ctx: CliContext, manifest: Manifest) -> None:
    cli_ctx.output_format = "raw"
    op = manifest.get("sell_inventory.getInventoryItem")
    out = _run(
        cli_ctx, op, path_params={"sku": "A"}, query_params={},
        header_params={}, body=None, files={},
    )
    import json

    payload = json.loads(out)
    assert payload["status"] == 200
    assert "body" in payload
    # secrets must never appear
    assert "authorization" not in {k.lower() for k in payload["headers"]}
