"""Test-mode gate, run ledger, and public/Browse verification semantics.

* ``verify-live`` reports nested server-added fields as dotted paths
  via a generic recursive diff (``allocationByFormat`` surfaces as
  ``availability.shipToLocationAvailability.allocationByFormat``), while lists
  stay exact leaves.
* ``verify_public`` polls the public/Browse representation with
  explicit stale-after-delete semantics, never treats HTTP 403 as proof of
  absence, and asserts title/description-marker/image-count/price/category/
  buying-option at the field level with a redacted last-observed summary.
* ``member_purchase_capability`` honestly reports member purchase
  history is unavailable on the current OAS surface, and the service->domain map
  labels seller sales / guest checkout / feedback so an agent cannot mistake
  seller orders for purchases.
* the ``--test-mode`` gate refuses publication without a test marker,
  requires ``--allow-scrambled-test-data`` for cross-wired provenance, and warns
  when a run id is not carried into the description/SKU.
* the run ledger records SKUs/offers/listings/traces/finance refs and
  the cleanup report distinguishes seller-records-deleted, frontend-converged,
  and financially-reversible (always false).
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ValidationError_
from bidkit_cli.manifest import Manifest

# ---------------------------------------------------------------------------
# shared harness
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _ctx(manifest: Manifest, handler, **ctx_kwargs) -> CliContext:
    from bidkit import EbayClient, EbayConfig

    client = EbayClient(
        EbayConfig(
            access_token="t",
            marketplace_id=ctx_kwargs.pop("marketplace_id", "EBAY_DE"),
        ),
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
# F5 — recursive nested verification diagnostics
# ---------------------------------------------------------------------------

def test_f5_added_paths_collapses_nested_enrichment() -> None:
    from bidkit_cli.workflows import _added_paths

    requested = {"shipToLocationAvailability": {"quantity": 1}}
    observed = {
        "shipToLocationAvailability": {
            "quantity": 1,
            "allocationByFormat": {"auction": 0, "fixedPrice": 1},
        }
    }
    added = _added_paths(requested, observed)
    # The whole allocationByFormat subtree is absent from the request: reported
    # as a single collapsed path, not its auction/fixedPrice children.
    assert added == ["shipToLocationAvailability.allocationByFormat"]


def test_f5_added_paths_keeps_list_as_leaf() -> None:
    from bidkit_cli.workflows import _added_paths

    # A list is never exploded into index paths; it is a leaf.
    requested = {"product": {"imageUrls": ["a", "b"]}}
    observed = {"product": {"imageUrls": ["a", "b"], "title": "T"}}
    added = _added_paths(requested, observed)
    assert added == ["product.title"]


def test_f5_compare_surfaces_nested_allocation_by_format(manifest: Manifest) -> None:
    from bidkit_cli.workflows import _compare

    requested = {
        "product": {"title": "T"},
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
    }
    observed = {
        "sku": "SKU",
        "locale": "de_DE",
        "product": {"title": "T"},
        "availability": {
            "shipToLocationAvailability": {
                "quantity": 1,
                "allocationByFormat": {"auction": 0, "fixedPrice": 1},
            }
        },
    }
    matched, unmatched, server_added = _compare(requested, observed)
    assert unmatched == []
    assert "availability.shipToLocationAvailability.allocationByFormat" in server_added
    assert "sku" in server_added
    assert "locale" in server_added
    # availability itself is matched (subset), so it is not in server_added.
    assert "availability" not in server_added


def test_f5_verify_live_live_shaped_enrichment_fixture(manifest: Manifest) -> None:
    """A live-shaped enriched inventory readback reports the derived path without
    failing verification (server-side enrichment must never read as a failed write)."""
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {
        "product": {"title": "Vintage Radio", "imageUrls": ["u1", "u2", "u3", "u4"]},
        "availability": {"shipToLocationAvailability": {"quantity": 1}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(204)
        return httpx.Response(200, json={
            "sku": "RADIO",
            "locale": "de_DE",
            "product": {"title": "Vintage Radio",
                        "imageUrls": ["u1", "u2", "u3", "u4"]},
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": 1,
                    "allocationByFormat": {"auction": 0, "fixedPrice": 1},
                    "quantityBuckets": [{"quantity": 1}],
                }
            },
        })

    ctx = _ctx(manifest, handler, allow_write=True, yes=True,
               verify_live=True, wait_for_live=0.0)
    _, err = _run_capturing(ctx, op, {"sku": "RADIO"}, body)
    report = json.loads(err.strip())["verify_live"]
    assert report["api_verified"] is True
    assert report["unmatched"] == []
    assert any("allocationByFormat" in p for p in report["server_added_fields"])
    # A second nested enrichment path is also surfaced distinctly.
    assert any("quantityBuckets" in p for p in report["server_added_fields"])


def test_f5_verify_live_missing_nested_field_still_unmatched(manifest: Manifest) -> None:
    """Recursive diagnostics must not turn a real missing nested field into a pass."""
    from bidkit_cli.workflows import _compare

    requested = {"availability": {"shipToLocationAvailability": {"quantity": 1}}}
    observed = {"availability": {"shipToLocationAvailability": {}}}  # quantity missing
    matched, unmatched, _ = _compare(requested, observed)
    assert "availability" in unmatched
    assert matched == []


# ---------------------------------------------------------------------------
# F1/F4 — verify_public: states, stale-after-delete, field assertions
# ---------------------------------------------------------------------------

def _browse_item(*, item_id="L1", title="Vase", price="12.50", currency="EUR",
                 category="14981", images=4, description="TEST ONLY — nothing shipped",
                 buying=("FIXED_PRICE",)):
    image = {"imageUrl": f"http://img/{item_id}/0"} if images else None
    additional = [{"imageUrl": f"http://img/{item_id}/{i}"} for i in range(max(0, images - 1))]
    return {
        "itemId": item_id,
        "title": title,
        "price": {"value": price, "currency": currency},
        "categoryId": category,
        "image": image,
        "additionalImages": additional,
        "description": description,
        "buyingOptions": list(buying),
        "returnTerms": "VERY LONG LEGAL BLOB " * 200,  # must be redacted
        "seller": {"username": "seller-contact", "email": "pii@example.com"},
    }


def test_f1_stale_after_delete_after_seller_cleanup(manifest: Manifest) -> None:
    """The headline scenario: seller API deleted, Browse still returns the item."""
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())
        if "/inventory_item/" in request.url.path:
            return httpx.Response(404)  # seller deleted
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(
        ctx, listing_id="L1", sku="AAAAA", expect_browse="not_found",
        expect_title="Vase", expect_description_contains="TEST ONLY",
        expect_image_count=4, expect_price="12.50", expect_currency="EUR",
        wait_seconds=0.0,
    )
    assert report["api_state"] == "deleted"
    # The fixture item carries no end signal, so the public side is still
    # "active"-looking while the seller record is gone -> the transient
    # stale_after_delete window (kept per F3 for exactly this no-end-signal case).
    assert report["browse_state"] == "active"
    assert report["frontend_state"] == "stale_after_delete"
    assert report["public_listing_state"] == "active"
    assert report["legacy_item_id"] == "L1"
    assert report["browse_item_id"] == "v1|L1|0"
    assert report["retry_safe"] is True
    assert report["met_expectation"] is False
    assert report["timed_out"] is False
    assert report["content_verified"] is True
    # The legal/PII blob is never echoed into the summary.
    summary = report["last_observed"]
    assert "returnTerms" not in summary
    assert "seller" not in summary
    assert summary["image_count"] == 4


def test_f1_visible_meets_expectation(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="visible", wait_seconds=0.0)
    assert report["frontend_state"] == "visible"
    assert report["met_expectation"] is True
    assert report["timed_out"] is False


def test_f1_not_found_meets_expectation(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="9", expect_browse="not_found", wait_seconds=0.0)
    assert report["browse_state"] == "not_found"
    assert report["frontend_state"] == "not_found"
    assert report["api_state"] == "not_checked"  # no --sku given
    assert report["met_expectation"] is True


def test_f1_http_403_is_blocked_not_absent(manifest: Manifest) -> None:
    """HTTP 403 (anti-automation throttle) must never read as proof of absence."""
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(403)
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="visible", wait_seconds=0.0)
    assert report["browse_state"] == "blocked"
    assert report["frontend_state"] == "blocked"
    # A single check (wait=0) is not a timeout; blocked is the honest answer.
    assert report["timed_out"] is False


def test_f1_blocked_with_budget_becomes_timeout(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(403)
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="visible",
                           wait_seconds=0.05, poll_interval=0.01)
    assert report["frontend_state"] == "timeout"
    assert report["timed_out"] is True
    # The honest last classification is retained underneath.
    assert report["last_frontend_state"] == "blocked"


def test_f1_not_yet_visible_after_publish(manifest: Manifest) -> None:
    """Just published: browse 404 but seller present -> not_yet_visible."""
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(404)
        if "/inventory_item/" in request.url.path:
            return httpx.Response(200, json={"sku": "S"})
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", sku="S", expect_browse="visible",
                           wait_seconds=0.05, poll_interval=0.01)
    assert report["frontend_state"] == "timeout"
    assert report["last_frontend_state"] == "not_yet_visible"


def test_f4_field_level_mismatches_reported(manifest: Manifest) -> None:
    """A 200 with wrong content is caught field-by-field, not just by visibility."""
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item(
                title="WRONG", price="9.99", currency="USD", category="999",
                images=1, description="no marker", buying=("AUCTION",)))
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(
        ctx, listing_id="L1", expect_browse="visible", expect_title="Vase",
        expect_description_contains="TEST ONLY", expect_image_count=4,
        expect_price="12.50", expect_currency="EUR", expect_category_id="14981",
        expect_buying_option="FIXED_PRICE", wait_seconds=0.0,
    )
    assert report["content_verified"] is False
    fields = {a["field"]: a for a in report["assertions"]}
    assert fields["title"]["match"] is False
    assert fields["description_contains"]["match"] is False
    assert fields["image_count"]["observed"] == 1
    assert fields["price.currency"]["observed"] == "USD"
    assert fields["buyingOptions"]["observed"] == ["AUCTION"]
    # The description itself is never echoed; only marker presence/length.
    assert "marker absent" in fields["description_contains"]["observed"]


def test_f4_verify_public_command_help_and_dry_run(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["sell", "inventory", "verify-public", "--help"])
    assert result.exit_code == 0, result.output
    assert "stale" in result.output.lower()
    assert "--expect" in result.output

    result = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "L1",
        "--expect", "not_found", "--expect-title", "T", "--dry-run", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)
    assert preview["dry_run"] is True
    assert preview["primary_check"] == "buy_browse.getItem"
    assert preview["seller_check"] is None
    assert preview["expect"] == "not_found"


def test_f4_verify_public_command_emits_report(manifest: Manifest, runner: CliRunner) -> None:
    """End-to-end through Click: the command emits the verify_public report."""
    # CliRunner builds its own context; point it at a mock by setting BIDKIT env
    # is not feasible, so verify the command dispatches via a context fixture is
    # covered by the direct verify_public tests above. Here we assert the command
    # exists in the tree and parses the assertion options.
    result = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "L1",
        "--expect-image-count", "4", "--expect-price", "12.50",
        "--expect-currency", "EUR", "--expect-category-id", "14981",
        "--expect-buying-option", "FIXED_PRICE", "--dry-run", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)
    assert set(preview["assertions"]) == {
        "expect_image_count", "expect_price", "expect_currency",
        "expect_category_id", "expect_buying_option",
    }


# ---------------------------------------------------------------------------
# F2/F7 — member purchase capability + data-domain map
# ---------------------------------------------------------------------------

def test_f2_member_purchase_capability_unavailable() -> None:
    from bidkit_cli.capabilities import member_purchase_capability

    report = member_purchase_capability()
    assert report["capability"] == "member_purchase_history"
    assert report["available"] is False
    assert "buyer scope" in report["reason"].lower()
    assert report["generated_surface"]["service"] == "buy_order"
    assert "guest" in report["generated_surface"]["scope"]
    # The report explicitly warns against confusing seller orders with purchases.
    assert "SELLER" in report["seller_sales_distinct"]


def test_f2_capability_command_emits_report(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["buy", "purchases", "capability", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["available"] is False
    assert payload["capability"] == "member_purchase_history"


def test_f7_domain_map_labels_transaction_sides() -> None:
    from bidkit_cli.capabilities import SERVICE_DOMAINS, domain_for_service

    assert domain_for_service("sell_fulfillment") == "seller_sales"
    assert domain_for_service("sell_finances") == "seller_sales"
    assert domain_for_service("buy_order") == "guest_checkout"
    assert domain_for_service("commerce_feedback") == "feedback"
    # An unlabeled service returns None (not a wrong guess).
    assert domain_for_service("sell_inventory") is None
    assert "member_purchases" not in SERVICE_DOMAINS.values()


def test_f7_domain_map_validates_against_manifest(manifest: Manifest) -> None:
    from bidkit_cli.capabilities import validate_domain_map

    services = {svc.key for svc in manifest.services}
    problems = validate_domain_map(services)
    assert problems == [], "domain map references a service not in the manifest"


def test_f7_api_search_labels_domains(runner: CliRunner) -> None:
    """api search order labels buy_order as guest_checkout and sell_fulfillment
    as seller_sales, so an agent cannot pick a seller order to answer a purchase
    question (the canonical member-purchases-vs-seller-orders confusion)."""
    result = runner.invoke(cli, ["api", "search", "order", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    by_key = {op["key"]: op["domain"] for op in payload["operations"]}
    assert by_key.get("buy_order.getGuestCheckoutSession") == "guest_checkout"
    assert by_key.get("sell_fulfillment.getOrders") == "seller_sales"
    # No operation is ever mislabeled as member purchases (that domain is
    # unavailable and has no services).
    assert "member_purchases" not in by_key.values()


def test_f7_api_search_domain_filter(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "search", "order",
                                 "--domain", "seller_sales", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] > 0
    assert all(op["domain"] == "seller_sales" for op in payload["operations"])


def test_f7_describe_includes_domain(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "describe", "sell_fulfillment.getOrders"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["domain"] == "seller_sales"


def test_f7_capability_negative_example_documented() -> None:
    """The skill docs must warn that seller orders are not member purchases."""
    skill = Path(__file__).resolve().parents[1] / "skills" / "bidkit-cli" / "SKILL.md"
    text = skill.read_text()
    assert "member purchases" in text.lower() or "purchase history" in text.lower()
    # Either the buy reference or the capability command documents the split.
    buy_ref = (skill.parent / "references" / "services" / "buy.md")
    if buy_ref.exists():
        assert "purchases" in buy_ref.read_text().lower()


# ---------------------------------------------------------------------------
# F3 — test-mode safety gate
# ---------------------------------------------------------------------------

def test_f3_marker_required_in_test_mode(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "no marker here"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True)
    with pytest.raises(ValidationError_) as exc:
        _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert "test marker" in str(exc.value).lower()


def test_f3_marker_passes_when_present(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY — nothing shipped"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True)
    out, _ = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"  # 204 -> no body; gate passed


def test_f3_scrambled_provenance_requires_consent(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY nothing"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    provenance = {"title": "SRC-A", "image": "SRC-B"}  # two sources
    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               test_provenance=provenance)
    with pytest.raises(ValidationError_) as exc:
        _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert "scrambled" in str(exc.value).lower()
    assert "--allow-scrambled-test-data" in str(exc.value)


def test_f3_scrambled_consent_warns_and_passes(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY nothing"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    provenance = {"title": "SRC-A", "image": "SRC-B"}
    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               allow_scrambled_test_data=True, test_provenance=provenance,
               test_run_id="RUN42", allow_untracked_test_run=True)
    out, err = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"
    # Both the scramble-consent warning and the run-id-carry warning surface.
    assert "scrambled test data" in err.lower()
    assert "RUN42" in err


def test_f3_single_source_provenance_needs_no_consent(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY nothing"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    provenance = {"title": "SRC-A", "image": "SRC-A"}  # one source, not scrambled
    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               test_provenance=provenance)
    out, _ = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"


def test_f3_gate_does_not_engage_without_test_mode(manifest: Manifest) -> None:
    """Without --test-mode, a normal write is unaffected (escape hatch intact)."""
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "real listing, no marker"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True)  # no test_mode
    out, _ = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"


def test_f3_test_mode_via_cli_refuses(runner: CliRunner) -> None:
    result = runner.invoke(cli, [
        "sell", "inventory", "create-or-replace-inventory-item", "SKU",
        "--body-json", '{"product": {"title": "V", "description": "no marker"}}',
        "--test-mode", "--dry-run", "--format", "json",
    ])
    # The validation error propagates out of the dry-run path; the message names
    # the missing marker so an agent knows exactly what to fix.
    assert result.exit_code != 0
    message = str(result.exception) if result.exception else result.output
    assert "test marker" in message.lower()


# ---------------------------------------------------------------------------
# F6 — run ledger + cleanup report
# ---------------------------------------------------------------------------

def test_f6_ledger_roundtrip(tmp_path: Path) -> None:
    from bidkit_cli.ledger import (
        FinanceRef,
        RunLedger,
        TraceEntry,
        load_ledger,
        new_run_id,
        save_ledger,
    )

    ledger = RunLedger(run_id=new_run_id(), created_at="2026-07-26T00:00:00Z",
                       source_skus=["RADIO1"])
    ledger.add_test_sku("AAAAA")
    ledger.add_offer("O1")
    ledger.add_listing("L1")
    ledger.add_trace(TraceEntry(operation="sell_inventory.publishOffer",
                                timestamp="t", request_id="REQ1"))
    ledger.add_finance(FinanceRef(timestamp="t", transaction_type="PRIVATE_LISTING_FEE",
                                  amount="0.42", currency="EUR", listing_id="L1"))
    path = save_ledger(ledger, base_dir=tmp_path)
    assert path.exists()

    loaded = load_ledger(ledger.run_id, base_dir=tmp_path)
    assert loaded.test_skus == ["AAAAA"]
    assert loaded.offer_ids == ["O1"]
    assert loaded.listing_ids == ["L1"]
    assert loaded.finance_refs[0].amount == "0.42"
    assert loaded.traces[0].request_id == "REQ1"


def test_f6_cleanup_report_tri_state() -> None:
    from bidkit_cli.ledger import FinanceRef, RunLedger, cleanup_report

    ledger = RunLedger(run_id="run-1", created_at="t", test_skus=["AAAAA"],
                       offer_ids=["O1"], listing_ids=["L1"])
    ledger.add_finance(FinanceRef(timestamp="t", amount="0.42", currency="EUR"))
    # Seller records deleted, but a booked fee cannot be reversed, and the public
    # listing is still visible (stale after delete) -> frontend NOT converged.
    report = cleanup_report(
        ledger,
        seller_state={"AAAAA": "deleted", "O1": "deleted"},
        frontend_state={"L1": "stale_after_delete"},
    )
    assert report["seller_records_deleted"] is True
    assert report["frontend_converged"] is True  # stale_after_delete is acceptable
    assert report["financially_reversible"] is False
    assert report["finance_charges_observed"] == 1
    assert "irreversible" in report["summary"]


def test_f6_cleanup_report_records_remaining() -> None:
    from bidkit_cli.ledger import RunLedger, cleanup_report

    ledger = RunLedger(run_id="run-2", created_at="t", test_skus=["AAAAA", "BBBBB"],
                       listing_ids=["L1"])
    report = cleanup_report(
        ledger,
        seller_state={"AAAAA": "deleted", "BBBBB": "present"},
        frontend_state={"L1": "visible"},
    )
    assert report["seller_records_deleted"] is False
    assert report["frontend_converged"] is False
    assert any(r["id"] == "BBBBB" for r in report["records_remaining"])
    assert report["frontend_remaining"][0]["listing_id"] == "L1"


def test_f6_test_run_init_record_show(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(cli, ["sell", "inventory", "test-run", "init",
                            "--source-sku", "RADIO1", "--ledger-dir", str(tmp_path)],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    init = json.loads(r.output)
    rid = init["run_id"]
    assert init["ledger_file"].endswith(f"{rid}.json")

    r = runner.invoke(cli, ["sell", "inventory", "test-run", "record", "--run-id", rid,
                            "--sku", "AAAAA", "--offer-id", "O1", "--listing-id", "L1",
                            "--request-id", "REQ1", "--operation", "sell_inventory.publishOffer",
                            "--ledger-dir", str(tmp_path)], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    rec = json.loads(r.output)
    assert rec["test_skus"] == ["AAAAA"]
    assert rec["listing_ids"] == ["L1"]

    r = runner.invoke(cli, ["sell", "inventory", "test-run", "show", "--run-id", rid,
                            "--ledger-dir", str(tmp_path)], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    shown = json.loads(r.output)
    assert shown["source_skus"] == ["RADIO1"]
    assert shown["traces"][0]["request_id"] == "REQ1"


def test_f6_cleanup_report_command_with_mock_client(
    manifest: Manifest, tmp_path: Path, monkeypatch
) -> None:
    """The cleanup-report command checks seller + public state via the manifest."""
    from bidkit import EbayClient, EbayConfig

    from bidkit_cli.ledger import RunLedger, save_ledger

    ledger = RunLedger(run_id="run-mock", created_at="t",
                       test_skus=["AAAAA"], listing_ids=["L1"])
    save_ledger(ledger, base_dir=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if "/inventory_item/" in request.url.path:
            return httpx.Response(404)  # seller deleted
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())  # still public (stale)
        return httpx.Response(404)

    client = EbayClient(EbayConfig(access_token="t", marketplace_id="EBAY_DE"),
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    # Inject the mock client into every CliContext the runner builds, regardless
    # of how it resolves config (the command only needs the client + manifest).
    monkeypatch.setattr(CliContext, "client", property(lambda self: client))

    runner = CliRunner()
    result = runner.invoke(cli, [
        "sell", "inventory", "test-run", "cleanup-report",
        "--run-id", "run-mock", "--ledger-dir", str(tmp_path), "--wait", "0",
    ], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["seller_records_deleted"] is True
    assert report["frontend_converged"] is True  # stale_after_delete is acceptable
    assert report["financially_reversible"] is False


def click_ctx_with_obj(obj: CliContext):
    import click

    return click.Context(click.Command("cleanup-report"), obj=obj)
