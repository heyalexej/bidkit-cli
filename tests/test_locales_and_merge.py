"""Marketplace locales, replace-like merge, verify-live, preflight limits.

* EBAY_DE locale: ``--content-language`` / ``--marketplace-locale`` derive the
  Content-Language eBay needs for German listings, surfaced in the dry-run preview
  and ``config locales``; no unknown-header escape hatch required.
* ``updateOffer`` is replace-like: ``--merge`` read/merge/write preserves
  omitted fields (listingPolicies, flags); help/describe mark it; an error after a
  write carries a non-idempotent-retry hint.
* frontend propagation: ``--verify-live`` polls the API readback and reports
  "API updated; frontend not yet confirmed" instead of implying convergence.
* title length is preflight-validated against the marketplace limit.
* publish taxonomy errors (25002/25007/25718) get an actionable hint.
* ``auth doctor --check-network`` requests the application scope only.
* ``api schema --model`` emits a valid enum schema instead of crashing.
* the 24-image inventory limit is preflight-validated.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout

import httpx2
import pytest
from bidkit import EbayClient, EbayConfig
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import EXIT_VALIDATION, ApiError, ValidationError_
from bidkit_cli.manifest import Manifest
from bidkit_cli.workflows import (
    REPLACE_LIKE_OPS,
    deep_merge,
    enrich_publish_error,
    is_replace_like,
)


def _ctx(manifest: Manifest, handler, **ctx_kwargs) -> CliContext:
    client = EbayClient(
        EbayConfig(access_token="t", marketplace_id=ctx_kwargs.pop("marketplace_id", "EBAY_US")),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
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


def _dry_run(args: list[str]) -> dict:
    result = CliRunner().invoke(cli, [*args, "--dry-run", "--format", "json"])
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    return json.loads(result.output)


def _run_capturing(ctx: CliContext, op, path_params: dict, body: dict) -> tuple[str, str]:
    """Run execute and return (stdout, stderr) text (verify-live writes stderr)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        execute(ctx, op, path_params=path_params, query_params={},
                header_params={}, body=body, files={})
    return out_buf.getvalue(), err_buf.getvalue()


# ---------------------------------------------------------------------------
# F1 — EBAY_DE locale / content-language
# ---------------------------------------------------------------------------

def test_f1_marketplace_locale_derives_german_languages(manifest: Manifest) -> None:
    """``--marketplace EBAY_DE --marketplace-locale`` resolves de-DE."""
    from bidkit_cli.config import load_effective_config

    config = load_effective_config(
        config_path=None, environment=None, marketplace="EBAY_DE",
        timeout=None, max_retries=None, marketplace_locale=True,
    )
    assert config.marketplace_id == "EBAY_DE"
    assert config.content_language == "de-DE"
    assert config.accept_language == "de-DE"


def test_f1_content_language_override_wins(manifest: Manifest) -> None:
    """An explicit --content-language takes precedence over marketplace derivation."""
    from bidkit_cli.config import load_effective_config

    config = load_effective_config(
        config_path=None, environment=None, marketplace="EBAY_DE",
        timeout=None, max_retries=None, marketplace_locale=True,
        content_language="fr-FR",
    )
    assert config.content_language == "fr-FR"
    # accept_language still derives from the marketplace when not overridden.
    assert config.accept_language == "de-DE"


def test_f1_dry_run_shows_resolved_locale(manifest: Manifest) -> None:
    preview = _dry_run([
        "sell", "inventory", "create-or-replace-inventory-item", "SKU",
        "--body-json", '{"product": {"title": "x"}}',
        "--marketplace", "EBAY_DE", "--marketplace-locale",
    ])
    assert preview["marketplace"] == "EBAY_DE"
    assert preview["content_language"] == "de-DE"
    assert preview["accept_language"] == "de-DE"


def test_f1_dry_run_shows_explicit_content_language(manifest: Manifest) -> None:
    preview = _dry_run([
        "sell", "inventory", "create-or-replace-inventory-item", "SKU",
        "--body-json", '{"product": {"title": "x"}}',
        "--content-language", "de-DE",
    ])
    assert preview["content_language"] == "de-DE"


def test_f1_config_locales_command(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "locales", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    rows = {row["marketplace_id"]: row for row in payload["marketplaces"]}
    assert rows["EBAY_DE"]["content_language"] == "de-DE"
    assert rows["EBAY_DE"]["title_limit"] == 80


def test_f1_no_global_accept_language_collision(runner: CliRunner) -> None:
    """The per-operation --accept-language header option still works (no global shadow)."""
    preview = _dry_run(["buy", "browse", "get-item", "ITEM1", "--accept-language", "de"])
    assert preview["headers"] == {"Accept-Language": "de"}


# ---------------------------------------------------------------------------
# F2 — updateOffer replace-like + --merge
# ---------------------------------------------------------------------------

def test_f2_replace_like_ops_known(manifest: Manifest) -> None:
    assert "sell_inventory.updateOffer" in REPLACE_LIKE_OPS
    assert "sell_inventory.createOrReplaceInventoryItem" in REPLACE_LIKE_OPS
    assert is_replace_like(manifest.get("sell_inventory.updateOffer"))
    assert not is_replace_like(manifest.get("sell_inventory.getOffer"))


def test_f2_describe_marks_replace_like(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "describe", "sell_inventory.updateOffer"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["replace_like"] is True


def test_f2_help_carries_replace_like_note(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["sell", "inventory", "update-offer", "--help"])
    assert result.exit_code == 0, result.output
    assert "Replace-like" in result.output
    assert "--merge" in result.output


def test_f2_merge_preserves_omitted_fields(manifest: Manifest) -> None:
    """--merge GETs current state and preserves omitted fields (listingPolicies/flags)."""
    op = manifest.get("sell_inventory.updateOffer")
    put_body: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            return httpx2.Response(200, json={
                "offerId": "O1",
                "listingPolicies": {"fulfillmentPolicyId": "FP1"},
                "pricingSummary": {"price": {"value": "10.00", "currency": "USD"}},
                "availableQuantity": 5,
                "includeCatalogProductDetails": True,
                "hideBuyerDetails": False,
            })
        put_body.update(json.loads(request.content))
        return httpx2.Response(200, json={"offerId": "O1"})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, merge=True)
    buf = io.StringIO()
    patch = {"pricingSummary": {"price": {"value": "12.50", "currency": "USD"}}}
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"offerId": "O1"}, query_params={},
                header_params={}, body=patch, files={})
    # The patched price is applied...
    assert put_body["pricingSummary"]["price"]["value"] == "12.50"
    # ...and the omitted fields are preserved, not reverted to defaults.
    assert put_body["listingPolicies"]["fulfillmentPolicyId"] == "FP1"
    assert put_body["availableQuantity"] == 5
    assert put_body["includeCatalogProductDetails"] is True


def test_f2_merge_over_create_passes_through(manifest: Manifest) -> None:
    """A 404 on the read (the 'create' half) leaves the provided body intact."""
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            return httpx2.Response(404, json={"errors": []})
        return httpx2.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, merge=True)
    body = {"product": {"title": "New"}}
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "SKU"}, query_params={},
                header_params={}, body=body, files={})


def test_f2_deep_merge_semantics() -> None:
    base = {"a": 1, "nested": {"x": 1, "y": 2}, "list": [1, 2]}
    patch = {"nested": {"y": 99}, "list": [9]}
    merged = deep_merge(base, patch)
    assert merged == {"a": 1, "nested": {"x": 1, "y": 99}, "list": [9]}


def test_f2_dry_run_merge_annotation(manifest: Manifest) -> None:
    """--merge in dry-run annotates the preview (it cannot fetch without network)."""
    preview = _dry_run([
        "sell", "inventory", "update-offer", "O1",
        "--body-json", '{"pricingSummary": {"price": {"value": "9.99", "currency": "USD"}}}',
        "--merge",
    ])
    assert "merge" in preview
    assert "--merge would GET" in preview["merge"]


def test_f2_error_after_mutation_hint(manifest: Manifest) -> None:
    """A failed write carries a non-idempotent-retry hint (state may have changed)."""
    op = manifest.get("sell_inventory.updateOffer")

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"errors": [{"errorId": 99999, "message": "boom"}]})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True)
    with pytest.raises(ApiError) as exc:
        execute(ctx, op, path_params={"offerId": "O1"}, query_params={},
                header_params={},
                body={"pricingSummary": {"price": {"value": "9.99", "currency": "USD"}}},
                files={})
    assert exc.value.status == 400
    assert "remote state may have changed" in (exc.value.hint or "").lower()


# ---------------------------------------------------------------------------
# F3 — verify-live
# ---------------------------------------------------------------------------

def test_f3_verify_live_reports_convergence(manifest: Manifest) -> None:
    """--verify-live polls the readback and reports matched/unmatched fields."""
    op = manifest.get("sell_inventory.updateOffer")
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if request.method == "PUT":
            return httpx2.Response(200, json={"offerId": "O1"})
        # First readback lags (old description), second matches.
        if calls["n"] == 2:
            return httpx2.Response(200, json={
                "offerId": "O1",
                "pricingSummary": {"price": {"value": "12.50", "currency": "USD"}},
                "listingDescription": "OLD",
            })
        return httpx2.Response(200, json={
            "offerId": "O1",
            "pricingSummary": {"price": {"value": "12.50", "currency": "USD"}},
            "listingDescription": "NEW",
        })

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               verify_live=True, wait_for_live=5.0)
    out, err = _run_capturing(ctx, op, {"offerId": "O1"},
                              {"pricingSummary": {"price": {"value": "12.50", "currency": "USD"}},
                               "listingDescription": "NEW"})
    # stdout is the single operation result; the verify report is on stderr.
    assert json.loads(out)["offerId"] == "O1"
    report = json.loads(err.strip())["verify_live"]
    assert report["verified"] is True
    assert "listingDescription" in report["matched"]
    assert "frontend" in report["frontend_note"].lower()


def test_f3_verify_live_reports_unmatched(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.updateOffer")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "PUT":
            return httpx2.Response(200, json={"offerId": "O1"})
        # Readback never reflects the requested price.
        return httpx2.Response(200, json={
            "offerId": "O1",
            "pricingSummary": {"price": {"value": "10.00", "currency": "USD"}},
        })

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               verify_live=True, wait_for_live=0.0)
    out, err = _run_capturing(ctx, op, {"offerId": "O1"},
                              {"pricingSummary": {"price": {"value": "12.50", "currency": "USD"}}})
    assert json.loads(out)["offerId"] == "O1"
    report = json.loads(err.strip())["verify_live"]
    assert report["verified"] is False
    assert "pricingSummary" in report["unmatched"]
    assert "frontend" in report["frontend_note"].lower()


# ---------------------------------------------------------------------------
# F4 — title length preflight
# ---------------------------------------------------------------------------

def test_f4_title_over_limit_rejected_before_dispatch(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    ctx = _ctx(manifest, lambda r: httpx2.Response(204), marketplace_id="EBAY_DE")
    long_title = "A" * 81
    with pytest.raises(ValidationError_) as exc:
        execute(ctx, op, path_params={"sku": "SKU"}, query_params={},
                header_params={}, body={"product": {"title": long_title}}, files={})
    assert exc.value.exit_code == EXIT_VALIDATION
    assert "80" in exc.value.message
    assert "EBAY_DE" in exc.value.message


def test_f4_title_at_limit_passes(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    ctx = _ctx(manifest, lambda r: httpx2.Response(204), marketplace_id="EBAY_DE",
               allow_write=True, yes=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "SKU"}, query_params={},
                header_params={}, body={"product": {"title": "A" * 80}}, files={})


def test_f4_title_limit_cli_dry_run(manifest: Manifest) -> None:
    long_title = "A" * 81
    result = CliRunner().invoke(cli, [
        "sell", "inventory", "create-or-replace-inventory-item", "SKU",
        "--body-json", json.dumps({"product": {"title": long_title}}),
        "--marketplace", "EBAY_DE", "--dry-run", "--format", "json",
    ])
    # Invoking cli() directly raises the structured error (the JSON envelope is
    # produced by main()); the message names the marketplace limit.
    assert isinstance(result.exception, ValidationError_)
    assert result.exception.exit_code == EXIT_VALIDATION
    assert "80" in result.exception.message
    assert "EBAY_DE" in result.exception.message


# ---------------------------------------------------------------------------
# F5 — publish taxonomy error translation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", [25002, 25007, 25718])
def test_f5_known_publish_errors_get_hints(code: int) -> None:
    hint = enrich_publish_error(400, {"errors": [{"errorId": code}]})
    assert hint is not None
    assert str(code) not in hint or code == 25002  # hint is actionable, not just the code


def test_f5_missing_aspect_hint_names_taxonomy(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.publishOffer")

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"errors": [{"errorId": 25002}]})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               marketplace_id="EBAY_DE")
    with pytest.raises(ApiError) as exc:
        execute(ctx, op, path_params={"offerId": "O1"}, query_params={},
                header_params={}, body=None, files={})
    assert exc.value.status == 400
    assert "get-item-aspects-for-category" in (exc.value.hint or "")


def test_f5_unknown_error_has_no_curated_hint() -> None:
    assert enrich_publish_error(400, {"errors": [{"errorId": 12345}]}) is None


# ---------------------------------------------------------------------------
# F6 — auth doctor client-credentials scope
# ---------------------------------------------------------------------------

class _FakeAuth:
    def __init__(self, *, exc: Exception | None = None) -> None:
        self._exc = exc

    def access_token(self, client):  # noqa: ANN001
        if self._exc is not None:
            raise self._exc
        return "TOKEN"


class _FakeClient:
    def __init__(self, config, *, exc: Exception | None = None) -> None:
        self.http = None
        self.auth = _FakeAuth(exc=exc)
        self.config = config
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeConfig:
    """Duck-typed config: records the scope set the client-token request used."""

    def __init__(self, *, refresh_token: str = "rt",
                 scopes: tuple[str, ...] = (
                     "https://api.ebay.com/oauth/api_scope",
                     "https://api.ebay.com/oauth/api_scope/sell.item",
                 )) -> None:
        self.refresh_token = refresh_token
        self.scopes = scopes

    def model_copy(self, *, update: dict | None = None) -> _FakeConfig:
        refreshed = _FakeConfig(refresh_token=self.refresh_token, scopes=self.scopes)
        if update:
            for key, value in update.items():
                setattr(refreshed, key, value)
        return refreshed


def test_f6_check_network_restricts_to_application_scope(monkeypatch) -> None:
    from bidkit_cli.commands import auth as auth_mod

    built: list[_FakeConfig] = []

    def _fake_client(config, token_cache=None):
        built.append(config)
        return _FakeClient(config)

    monkeypatch.setattr("bidkit.EbayClient", _fake_client)
    monkeypatch.setattr("bidkit.FileTokenCache", lambda: None)
    report = auth_mod._check_network(_FakeConfig())
    assert report["ok"] is True
    assert report["token_type"] == "client_credentials"
    assert report["scope"] == "https://api.ebay.com/oauth/api_scope"
    # The config handed to the client was restricted to the application scope,
    # not the user-only scopes present in the source config.
    sent = built[0]
    assert sent.refresh_token is None
    assert sent.scopes == ("https://api.ebay.com/oauth/api_scope",)


def test_f6_check_user_token_still_uses_full_scopes(monkeypatch) -> None:
    """The user-token check must NOT be restricted to the application scope."""
    from bidkit_cli.commands import auth as auth_mod

    built: list[_FakeConfig] = []

    def _fake_client(config, token_cache=None):
        built.append(config)
        return _FakeClient(config)

    monkeypatch.setattr("bidkit.EbayClient", _fake_client)
    monkeypatch.setattr("bidkit.FileTokenCache", lambda: None)
    report = auth_mod._check_user_token(_FakeConfig())
    assert report["ok"] is True
    assert report["token_type"] == "user"
    # The full scope set is preserved for the user refresh-token exchange.
    assert "https://api.ebay.com/oauth/api_scope/sell.item" in built[0].scopes


# ---------------------------------------------------------------------------
# F7 — api schema --model for enums / non-Pydantic classes
# ---------------------------------------------------------------------------

def test_f7_schema_for_enum_emits_enum_schema(runner: CliRunner) -> None:
    result = runner.invoke(cli, [
        "api", "schema", "sell_inventory.createOrReplaceInventoryItem", "request",
        "--model", "ConditionEnum", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output)
    assert schema["title"] == "ConditionEnum"
    assert schema["type"] == "string"
    assert "NEW" in schema["enum"]


def test_f7_schema_for_request_model_still_works(runner: CliRunner) -> None:
    result = runner.invoke(cli, [
        "api", "schema", "sell_inventory.createOrReplaceInventoryItem", "request",
        "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output)
    assert "properties" in schema


def test_f7_schema_for_nonexistent_model(runner: CliRunner) -> None:
    result = runner.invoke(cli, [
        "api", "schema", "sell_inventory.createOrReplaceInventoryItem", "request",
        "--model", "DoesNotExist", "--format", "json",
    ])
    assert result.exit_code != 0
    assert "DoesNotExist" in (str(result.exception) + result.output)


# ---------------------------------------------------------------------------
# F8 — image count limit + media composition
# ---------------------------------------------------------------------------

def test_f8_too_many_images_rejected(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    ctx = _ctx(manifest, lambda r: httpx2.Response(204), allow_write=True, yes=True)
    urls = [f"https://i.ebayimg.com/images/g/{i}.JPG" for i in range(25)]
    with pytest.raises(ValidationError_) as exc:
        execute(ctx, op, path_params={"sku": "SKU"}, query_params={},
                header_params={}, body={"product": {"title": "ok", "imageUrls": urls}},
                files={})
    assert exc.value.exit_code == EXIT_VALIDATION
    assert "24" in exc.value.message


def test_f8_twenty_four_images_pass(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    ctx = _ctx(manifest, lambda r: httpx2.Response(204), allow_write=True, yes=True)
    urls = [f"https://i.ebayimg.com/images/g/{i}.JPG" for i in range(24)]
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "SKU"}, query_params={},
                header_params={}, body={"product": {"title": "ok", "imageUrls": urls}},
                files={})


def test_f8_update_offer_examples_document_merge_and_verify(manifest: Manifest) -> None:
    """The curated updateOffer examples teach the merge/verify workflow."""
    op = manifest.get("sell_inventory.updateOffer")
    commands = " ".join(ex.command for ex in op.examples)
    notes = " ".join(ex.note or "" for ex in op.examples)
    assert "--merge" in commands
    assert "verify-live" in commands
    lowered = notes.lower()
    assert "merge" in lowered or "replacement" in lowered or "verify" in lowered


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
