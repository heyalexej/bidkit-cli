"""verify-live subset comparison, multi-status success, publish hints, locale preview.

* ``verify-live`` must use a recursive *subset* comparison so normal
  eBay response enrichment (``availability.allocationByFormat``, server
  timestamps) no longer turns a successful write into a false failure. Lists stay
  exact (image order / list replacement is meaningful); a requested field that is
  entirely absent is still a real mismatch.
* a generated operation can return several success statuses
  (``updateOffer`` returns 200 JSON *or* 204 No Content). Help renders *all* of
  them, ``api schema ... response`` prefers a modeled success, and a 204 is a
  successful terminal result whose body is ``null``.
* the publish 25002 hint carries the actual missing-aspect names
  parsed from ``errors[].parameters[].value`` (``Produktart``, ``Marke``), not
  just a generic "an aspect is missing".
* dry-run previews a ``config_injected_headers`` block mirroring
  the SDK transport defaults, so an empty ``headers`` object no longer reads as
  "no language headers will be sent" for an EBAY_DE listing.
* F5 (Low/Medium) — the verify-live report distinguishes ``api_verified`` from
  ``frontend_verified`` (null = not checked, not "failed") and lists
  ``server_added_fields``.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout

import httpx
import pytest
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ApiError
from bidkit_cli.manifest import Manifest
from bidkit_cli.workflows import (
    _compare,
    _is_subset,
    enrich_publish_error,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _ctx(manifest: Manifest, handler, **ctx_kwargs) -> CliContext:
    from bidkit import EbayClient, EbayConfig

    client = EbayClient(
        EbayConfig(access_token="t", marketplace_id=ctx_kwargs.pop("marketplace_id", "EBAY_US")),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    for key, value in ctx_kwargs.items():
        setattr(ctx, key, value)
    return ctx


def _run_capturing(ctx: CliContext, op, path_params: dict, body) -> tuple[str, str]:
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        execute(ctx, op, path_params=path_params, query_params={},
                header_params={}, body=body, files={})
    return out_buf.getvalue(), err_buf.getvalue()


# ---------------------------------------------------------------------------
# F1 — recursive subset comparison
# ---------------------------------------------------------------------------

def test_f1_is_subset_allows_server_enrichment() -> None:
    requested = {"shipToLocationAvailability": {"quantity": 1}}
    enriched = {"shipToLocationAvailability": {
        "quantity": 1,
        "allocationByFormat": {"auction": 0, "fixedPrice": 1},
    }}
    assert _is_subset(requested, enriched) is True


def test_f1_is_subset_keeps_exact_list_comparison() -> None:
    # Image order / list replacement is meaningful: a reordered or partial list
    # is still a real mismatch.
    assert _is_subset(["a", "b"], ["b", "a"]) is False
    assert _is_subset(["a"], ["a", "b"]) is False
    assert _is_subset(["a", "b"], ["a", "b"]) is True


def test_f1_is_subset_absent_field_is_a_real_mismatch() -> None:
    # A requested dict against an absent (None) observed value must fail, not be
    # swallowed as "enrichment".
    assert _is_subset({"quantity": 1}, None) is False
    assert _is_subset({"quantity": 1}, {"availableQuantity": 1}) is False


def test_f1_is_subset_scalar_equality() -> None:
    assert _is_subset(1, 1) is True
    assert _is_subset("NEW", "NEW") is True
    assert _is_subset("NEW", "USED") is False


def test_f1_compare_reports_server_added_fields() -> None:
    requested = {"availability": {"shipToLocationAvailability": {"quantity": 1}}}
    observed = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": 1,
                "allocationByFormat": {"auction": 0, "fixedPrice": 1},
            }
        },
        "sku": "SKU",
        "locale": "de_DE",
    }
    matched, unmatched, server_added = _compare(requested, observed)
    assert matched == ["availability"]
    assert unmatched == []
    # Server-derived keys that were not part of the request are surfaced as a
    # diagnostic list, never as a failure.
    assert "sku" in server_added
    assert "locale" in server_added
    # Nested server enrichment is reported as a dotted
    # path (previously the selected-field flattener swallowed it).
    assert "availability.shipToLocationAvailability.allocationByFormat" in server_added


def test_f1_verify_live_no_longer_false_negatives_on_enrichment(manifest: Manifest) -> None:
    """A fresh inventory write whose availability is enriched with
    allocationByFormat must verify as matched."""
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {
        "product": {"title": "T"},
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(204)
        return httpx.Response(200, json={
            "sku": "SKU",
            "product": {"title": "T"},
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": 1,
                    "allocationByFormat": {"auction": 0, "fixedPrice": 1},
                }
            },
        })

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               verify_live=True, wait_for_live=0.0)
    out, err = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"  # 204 -> no body
    report = json.loads(err.strip())["verify_live"]
    assert report["api_verified"] is True
    assert "availability" in report["matched"]
    assert report["unmatched"] == []
    # The allocationByFormat enrichment surfaces as a
    # dotted path in server_added_fields (it is no longer hidden).
    assert any("allocationByFormat" in p for p in report["server_added_fields"])
    assert "sku" in report["server_added_fields"]


# ---------------------------------------------------------------------------
# F2 — multi-status success in help / schema / 204 terminal
# ---------------------------------------------------------------------------

def test_f2_help_renders_every_success_status(manifest: Manifest, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["sell", "inventory", "update-offer", "--help"])
    assert result.exit_code == 0, result.output
    assert "Success: 200 application/json; 204 No Content" in result.output


def test_f2_help_204_only_shows_no_content(manifest: Manifest, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["sell", "inventory", "delete-inventory-item", "--help"])
    assert result.exit_code == 0, result.output
    assert "Success: 204 No Content" in result.output


def test_f2_describe_lists_all_success_statuses(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "describe", "sell_inventory.updateOffer"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    statuses = [r["status"] for r in payload["responses"] if r["status"] in {"200", "204"}]
    assert statuses == ["200", "204"]


def test_f2_204_is_successful_terminal_with_null_body(manifest: Manifest) -> None:
    """A 204 response renders a successful terminal result whose body is null."""
    op = manifest.get("sell_inventory.updateOffer")
    ctx = _ctx(manifest, lambda r: httpx.Response(204), allow_write=True, yes=True)
    out, _ = _run_capturing(ctx, op, {"offerId": "O1"}, {})
    assert out.strip() == "null"


def test_f2_204_with_include_meta_has_status_and_null_data(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.updateOffer")
    ctx = _ctx(manifest, lambda r: httpx.Response(204), allow_write=True, yes=True,
               include_meta=True)
    out, _ = _run_capturing(ctx, op, {"offerId": "O1"}, {})
    payload = json.loads(out)
    assert payload["meta"]["status"] == 204
    assert payload["data"] is None


def test_f2_schema_response_prefers_modeled_success(runner: CliRunner) -> None:
    # updateOffer's first success is a modeled 200; schema resolves it even when
    # a 204 is also declared.
    result = runner.invoke(cli, [
        "api", "schema", "sell_inventory.updateOffer", "response", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output)
    assert "properties" in schema


# ---------------------------------------------------------------------------
# F3 — missing-aspect names parsed from error parameters
# ---------------------------------------------------------------------------

def test_f3_missing_aspects_extracted_from_parameters() -> None:
    payload = {"errors": [{"errorId": 25002, "parameters": [
        {"name": "0", "value": "Produktart"},
        {"name": "1", "value": "Marke"},
    ]}]}
    hint = enrich_publish_error(400, payload)
    assert hint is not None
    assert "Produktart" in hint
    assert "Marke" in hint
    assert "Missing required product aspects" in hint


def test_f3_missing_aspect_single_name() -> None:
    payload = {"errors": [{"errorId": 25002, "parameters": [
        {"name": "aspectName", "value": "Marke"}]}]}
    hint = enrich_publish_error(400, payload)
    assert hint is not None
    assert "Marke" in hint


def test_f3_no_parameters_still_actionable() -> None:
    hint = enrich_publish_error(400, {"errors": [{"errorId": 25002}]})
    assert hint is not None
    assert "get-item-aspects-for-category" in hint
    assert "Missing required product aspects" not in hint


def test_f3_aspect_names_surface_through_dispatch(manifest: Manifest) -> None:
    """A failing publishOffer surfaces the named aspects in the ApiError hint."""
    op = manifest.get("sell_inventory.publishOffer")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{
            "errorId": 25002,
            "parameters": [{"name": "0", "value": "Produktart"}],
        }]})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True)
    with __import__("pytest").raises(ApiError) as exc:
        execute(ctx, op, path_params={"offerId": "O1"}, query_params={},
                header_params={}, body=None, files={})
    hint = exc.value.hint or ""
    assert "Produktart" in hint
    assert "get-item-aspects-for-category" in hint


# ---------------------------------------------------------------------------
# F4 — dry-run config_injected_headers
# ---------------------------------------------------------------------------

def test_f4_dry_run_shows_sdk_default_locale_headers() -> None:
    result = CliRunner().invoke(cli, [
        "sell", "inventory", "create-or-replace-inventory-item", "SKU",
        "--body-json", '{"product": {"title": "x"}}',
        "--marketplace", "EBAY_DE", "--marketplace-locale",
        "--dry-run", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)
    # Explicit user/param headers are still empty (none supplied).
    assert preview["headers"] == {}
    # ...but the SDK-injected defaults make clear the locale headers WILL be sent.
    injected = preview["config_injected_headers"]
    assert injected["Accept"] == "application/json"
    assert injected["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_DE"
    assert injected["Content-Language"] == "de-DE"
    assert injected["Accept-Language"] == "de-DE"


def test_f4_dry_run_config_headers_reflect_config() -> None:
    """Even with no locale flags, the SDK defaults (Accept, marketplace, langs)
    are surfaced under config_injected_headers so an agent never reads an empty
    headers object as 'no headers will be sent'."""
    result = CliRunner().invoke(cli, [
        "sell", "inventory", "create-or-replace-inventory-item", "SKU",
        "--body-json", '{"product": {"title": "x"}}',
        "--dry-run", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)
    injected = preview["config_injected_headers"]
    # The structural contract: these defaults are always present and non-empty.
    assert injected["Accept"] == "application/json"
    assert injected["X-EBAY-C-MARKETPLACE-ID"]
    assert "Accept-Language" in injected
    assert "Content-Language" in injected


# ---------------------------------------------------------------------------
# F5 — api_verified vs frontend_verified
# ---------------------------------------------------------------------------

def test_f5_report_distinguishes_api_and_frontend_verification(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.updateOffer")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={"offerId": "O1"})
        return httpx.Response(200, json={
            "offerId": "O1",
            "pricingSummary": {"price": {"value": "12.50", "currency": "USD"}},
        })

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               verify_live=True, wait_for_live=0.0)
    _, err = _run_capturing(ctx, op, {"offerId": "O1"},
                            {"pricingSummary": {"price": {"value": "12.50", "currency": "USD"}}})
    report = json.loads(err.strip())["verify_live"]
    assert report["api_verified"] is True
    # frontend_verified is null: the public page is intentionally not polled,
    # and null means "not checked" — not "checked and failed".
    assert report["frontend_verified"] is None
    assert report["verified"] is report["api_verified"]  # backwards-compat alias
    assert "server_added_fields" in report
    note = report["frontend_note"].lower()
    assert "api state" in note
    assert "frontend_verified" in report["frontend_note"].lower()


def test_f5_report_unmatched_is_api_not_frontend(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.updateOffer")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={"offerId": "O1"})
        return httpx.Response(200, json={
            "offerId": "O1",
            "pricingSummary": {"price": {"value": "10.00", "currency": "USD"}},
        })

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               verify_live=True, wait_for_live=0.0)
    _, err = _run_capturing(ctx, op, {"offerId": "O1"},
                            {"pricingSummary": {"price": {"value": "12.50", "currency": "USD"}}})
    report = json.loads(err.strip())["verify_live"]
    assert report["api_verified"] is False
    assert report["frontend_verified"] is None
    assert "pricingSummary" in report["unmatched"]


def test_f5_verify_live_no_fields_reports_api_verified_false(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.updateOffer")
    ctx = _ctx(manifest, lambda r: httpx.Response(200, json={}),
               allow_write=True, yes=True, verify_live=True, wait_for_live=0.0)
    _, err = _run_capturing(ctx, op, {"offerId": "O1"}, {})
    report = json.loads(err.strip())["verify_live"]
    assert report["api_verified"] is False
    assert report["frontend_verified"] is None
    assert "reason" in report
