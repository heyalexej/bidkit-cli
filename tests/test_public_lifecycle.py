"""Public-listing lifecycle: Browse id normalization, ended/retained states, ledger.

* Browse ID normalization: a numeric ``--listing-id`` becomes
  ``v1|<legacy>|0`` before ``buy_browse.getItem``; both ids are in the output.
* ``createOffer`` test-mode gate reads the OAS ``listingDescription``
  field, so an OAS-correct body passes without inventing ``description``.
* ended/retained public records are modeled; ``--expect not-listed`` /
  ``active``; ``not_listed`` = seller deleted + public ended.
* auto-recording to the ledger on ``--test-run-id``; per-record,
  idempotent cleanup; finance-observation status (never a reversal guarantee).
* a ``--test-run-id`` not carried in description/SKU is refused unless
  ``--allow-untracked-test-run``.
* ``test-run execute`` plans, gates, and cleans up idempotently.
* verifier exit codes (non-zero on unmet expectation),
  ``public_listing_state``, ``content_verified``, separate ids.
* bounded Browse projection by default; ``--full`` retains the body.
* **F9–F14 + taxonomy** — stable error classification, HTML normalization,
  bounded retry, the capability policy, ``bidkit capabilities``, and
  ``auth doctor --show-capabilities``.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import UTC
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ApiError, ValidationError_
from bidkit_cli.manifest import Manifest

# ---------------------------------------------------------------------------
# shared harness (mirrors test_testmode_and_ledger)
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


def _run_capturing(ctx: CliContext, op, path_params: dict, body) -> str:
    out_buf = io.StringIO()
    with redirect_stdout(out_buf):
        execute(ctx, op, path_params=path_params, query_params={},
                header_params={}, body=body, files={})
    return out_buf.getvalue()


def _browse_item(*, item_id="v1|L1|0", title="Vase", price="12.50", currency="EUR",
                 end=None, availability=None, description="TEST ONLY — nothing shipped"):
    item = {
        "itemId": item_id, "title": title,
        "price": {"value": price, "currency": currency},
        "categoryId": "14981", "description": description,
        "buyingOptions": ["FIXED_PRICE"],
        "returnTerms": "VERY LONG LEGAL BLOB " * 200,
        "seller": {"username": "x", "email": "pii@example.com"},
    }
    if end is not None:
        item["itemEndDate"] = end
    if availability is not None:
        item["estimatedAvailability"] = availability
    return item


# ---------------------------------------------------------------------------
# F1 — Browse ID normalization
# ---------------------------------------------------------------------------

def test_f1_normalize_numeric_to_restful() -> None:
    from bidkit_cli.workflows import normalize_item_id

    assert normalize_item_id("358845110146") == ("v1|358845110146|0", "358845110146")
    # RESTful input round-trips; the legacy id is extracted.
    assert normalize_item_id("v1|358845110146|0") == ("v1|358845110146|0", "358845110146")


def test_f1_verify_public_sends_restful_id_and_reports_both(manifest: Manifest) -> None:
    """A numeric listing id reaches getItem as v1|<legacy>|0; both ids are output."""
    from bidkit_cli.workflows import verify_public

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            seen.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=_browse_item(item_id="v1|358845110146|0"))
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="358845110146", expect_browse="active",
                           wait_seconds=0.0)
    # The wire path received the RESTful form, not the bare numeric id.
    assert seen == ["v1|358845110146|0"]
    assert report["browse_item_id"] == "v1|358845110146|0"
    assert report["legacy_item_id"] == "358845110146"
    assert report["listing_id"] == "358845110146"
    assert report["browse_state"] == "active"


def test_f1_verify_public_command_dry_run_normalizes(runner: CliRunner) -> None:
    result = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "358845110146",
        "--expect", "not_listed", "--dry-run", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)
    assert preview["browse_item_id"] == "v1|358845110146|0"
    assert preview["legacy_item_id"] == "358845110146"


# ---------------------------------------------------------------------------
# F2 — createOffer uses listingDescription
# ---------------------------------------------------------------------------

def test_f2_create_offer_listing_description_satisfies_gate(manifest: Manifest) -> None:
    """An OAS-correct createOffer body (listingDescription only) passes the gate."""
    op = manifest.get("sell_inventory.createOffer")
    body = {"listingDescription": "TEST ONLY — nothing will be shipped."}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"offerId": "O1"})

    ctx = _ctx(manifest, handler, allow_write=True, allow_write_expert=True,
               yes=True, test_mode=True)
    out = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    payload = json.loads(out)
    assert payload["offerId"] == "O1"


def test_f2_create_offer_without_marker_refused(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOffer")
    body = {"listingDescription": "real listing, no marker"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"offerId": "O1"})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True)
    with pytest.raises(ValidationError_) as exc:
        _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert "test marker" in str(exc.value).lower()


def test_f2_create_offer_legacy_description_still_supported(manifest: Manifest) -> None:
    """The legacy `description` alias still satisfies the gate as a fallback."""
    op = manifest.get("sell_inventory.createOffer")
    body = {"description": "TEST ONLY — nothing will be shipped."}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"offerId": "O1"})

    ctx = _ctx(manifest, handler, allow_write=True, allow_write_expert=True,
               yes=True, test_mode=True)
    out = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert json.loads(out)["offerId"] == "O1"


# ---------------------------------------------------------------------------
# F3 — ended/retained states + --expect not-listed / active
# ---------------------------------------------------------------------------

def test_f3_not_listed_when_seller_deleted_and_public_ended(manifest: Manifest) -> None:
    """The headline cleanup state: seller gone AND public record ended/past."""
    from datetime import datetime, timedelta

    from bidkit_cli.workflows import verify_public

    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item(
                end=past,
                availability={"estimatedAvailabilityStatus": "OUT_OF_STOCK",
                              "estimatedRemainingQuantity": 0}))
        if "/inventory_item/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", sku="AAAAA",
                           expect_browse="not_listed", wait_seconds=0.0)
    assert report["browse_state"] == "ended"
    assert report["frontend_state"] == "not_listed"
    assert report["public_listing_state"] == "retained"
    assert report["met_expectation"] is True  # not_listed is satisfied


def test_f3_public_ended_when_seller_present(manifest: Manifest) -> None:
    from datetime import datetime, timedelta

    from bidkit_cli.workflows import verify_public

    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item(end=past))
        if "/inventory_item/" in request.url.path:
            return httpx.Response(200, json={"sku": "S"})
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", sku="S", expect_browse="active",
                           wait_seconds=0.0)
    assert report["browse_state"] == "ended"
    assert report["frontend_state"] == "public_ended"
    assert report["public_listing_state"] == "ended"
    assert report["met_expectation"] is False  # ended is not active


def test_f3_active_expectation_met_by_purchasable_item(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())  # no end date -> active
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="active", wait_seconds=0.0)
    assert report["met_expectation"] is True
    assert report["public_listing_state"] == "active"


def test_f3_visible_includes_retained_history(manifest: Manifest) -> None:
    """--expect visible is met by an ended (retained) public record too."""
    from datetime import datetime, timedelta

    from bidkit_cli.workflows import verify_public

    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item(end=past))
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="visible", wait_seconds=0.0)
    assert report["met_expectation"] is True


# ---------------------------------------------------------------------------
# F4 — auto-recording + finance status + per-record cleanup
# ---------------------------------------------------------------------------

def test_f4_auto_records_publish_to_ledger(manifest: Manifest, tmp_path: Path) -> None:
    """A publishOffer with --test-run-id auto-records the listing id."""
    from bidkit_cli.ledger import RunLedger, load_ledger, save_ledger

    ledger = RunLedger(run_id="run-auto", created_at="t")
    save_ledger(ledger, base_dir=tmp_path)

    op = manifest.get("sell_inventory.publishOffer")

    def handler(request: httpx.Request) -> httpx.Response:
        # Real publishOffer responses carry only listingId (+ warnings); the
        # offer id must come from the path param, not an invented body field.
        return httpx.Response(200, json={"listingId": "358845110146"})

    ctx = _ctx(manifest, handler, allow_write=True, allow_write_expert=True,
               yes=True, test_run_id="run-auto")
    with patch("bidkit_cli.ledger.default_ledger_dir", return_value=tmp_path):
        out = _run_capturing(ctx, op, {"offerId": "O9"}, None)
    payload = json.loads(out)
    assert payload["listingId"] == "358845110146"
    # The ledger now carries the listing + offer + an event, without an explicit
    # `test-run record` call.
    loaded = load_ledger("run-auto", base_dir=tmp_path)
    assert "358845110146" in loaded.listing_ids
    assert "O9" in loaded.offer_ids
    assert any(e.operation == "sell_inventory.publishOffer" for e in loaded.events)


def test_f4_cleanup_report_finance_status_and_per_record(tmp_path: Path) -> None:
    from bidkit_cli.ledger import RunLedger, cleanup_report

    ledger = RunLedger(run_id="r", created_at="t", test_skus=["AAAAA"],
                       offer_ids=["O1"], listing_ids=["L1"])
    report = cleanup_report(
        ledger,
        seller_state={"AAAAA": "deleted", "O1": "deleted"},
        frontend_state={"L1": "not_listed"},
        public_listing_state={"L1": "retained"},
    )
    assert report["finance_status"] == "not_checked"
    assert report["seller_records_deleted"] is True
    assert report["frontend_converged"] is True
    assert report["per_listing"][0]["public_record"] == "retained"
    assert "finance:" in report["summary"]


def test_f4_finance_charge_flips_status_irreversibly(tmp_path: Path) -> None:
    from bidkit_cli.ledger import FinanceRef, RunLedger, cleanup_report

    ledger = RunLedger(run_id="r", created_at="t", test_skus=["A"])
    ledger.add_finance(FinanceRef(timestamp="t", amount="0.42", currency="EUR"))
    # A later "no charge observed" must not downgrade a charge already seen.
    ledger.record_finance_status("no_charge_observed")
    report = cleanup_report(ledger, seller_state={"A": "deleted"}, frontend_state={})
    assert ledger.finance_status == "charge_observed"
    assert report["finance_status"] == "charge_observed"


# ---------------------------------------------------------------------------
# F5 — run-id traceability enforcement
# ---------------------------------------------------------------------------

def test_f5_run_id_not_carried_is_refused(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY nothing"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               test_run_id="RUN-X")
    with pytest.raises(ValidationError_) as exc:
        _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert "--allow-untracked-test-run" in str(exc.value)


def test_f5_run_id_in_description_passes(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY run RUN-X"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               test_run_id="RUN-X")
    out = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"


def test_f5_override_allows_untracked(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "Vase", "description": "TEST ONLY nothing"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               test_run_id="RUN-X", allow_untracked_test_run=True)
    out = _run_capturing(ctx, op, {"sku": "SKU"}, body)
    assert out.strip() == "null"


# ---------------------------------------------------------------------------
# F7 — verifier exit codes + content_verified + public_listing_state
# ---------------------------------------------------------------------------

def test_f7_verify_public_command_exits_nonzero_on_unmet(manifest: Manifest,
                                                        runner: CliRunner) -> None:
    """verify-public exits 1 when the expectation is not met (assertion/CI mode)."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())  # active, not not_listed
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    from bidkit import EbayClient, EbayConfig
    mock = EbayClient(EbayConfig(access_token="t", marketplace_id="EBAY_DE"),
                      http_client=client)
    with patch.object(CliContext, "client", new=property(lambda self: mock)):
        result = runner.invoke(cli, [
            "sell", "inventory", "verify-public", "--listing-id", "1",
            "--expect", "not_listed", "--wait", "0", "--format", "json",
        ])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["met_expectation"] is False
    assert report["public_listing_state"] in {"active", "ended"}


def test_f7_content_verified_only_on_observed_200(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="not_found", wait_seconds=0.0)
    # No 200 observed -> never content_verified, even with no assertions.
    assert report["content_verified"] is False


# ---------------------------------------------------------------------------
# F8 — bounded Browse projection / --full
# ---------------------------------------------------------------------------

def test_f8_default_projection_drops_legal_blob(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="active", wait_seconds=0.0)
    summary = report["last_observed"]
    assert "returnTerms" not in summary
    assert "seller" not in summary
    assert "last_observed_full" not in report


def test_f8_full_retains_raw_body(manifest: Manifest) -> None:
    from bidkit_cli.workflows import verify_public

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())
        return httpx.Response(404)

    ctx = _ctx(manifest, handler)
    report = verify_public(ctx, listing_id="L1", expect_browse="active",
                           wait_seconds=0.0, full=True)
    assert report["last_observed_full"] is True
    assert "returnTerms" in report["last_observed"]


# ---------------------------------------------------------------------------
# F9–F14 + error taxonomy — classification, retry, capability policy
# ---------------------------------------------------------------------------

def test_taxonomy_500_access_denied_is_upstream_not_capability() -> None:
    """A 500 whose body says 'Access is denied' is upstream_error, retriable."""
    from bidkit_cli.classification import classify_response

    c = classify_response(500, operation="commerce_feedback.getItemsAwaitingFeedback",
                          body="<html>Access is denied</html>", content_type="text/html")
    assert c.kind == "upstream_error"
    assert c.retry is True
    assert c.normalized_body is not None
    assert "Access is denied" in c.normalized_body["body_preview"]


def test_taxonomy_403_is_capability_not_granted() -> None:
    from bidkit_cli.classification import classify_response

    c = classify_response(403, operation="sell_leads.getAllClassifiedLeads", body=None)
    assert c.kind == "capability_not_granted"
    assert c.retry is False


def test_taxonomy_401_is_account_not_eligible() -> None:
    from bidkit_cli.classification import classify_response

    c = classify_response(401, operation="sell_edelivery_international_shipping.getX")
    assert c.kind == "account_not_eligible"
    assert c.retry is False


def test_taxonomy_429_honors_retry_after() -> None:
    from bidkit_cli.classification import classify_response

    c = classify_response(429, operation="x.y", headers={"retry-after": "7"})
    assert c.kind == "rate_limited"
    assert c.retry_after == 7.0


def test_taxonomy_leads_500_not_retried_due_to_policy(manifest: Manifest) -> None:
    """Leads policy says retry=False, so a 500 is not retried even though 500 is
    normally retriable."""
    op = manifest.get("sell_leads.getAllClassifiedLeads")
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, content=b"<html>Access is denied</html>",
                              headers={"content-type": "text/html"})

    ctx = _ctx(manifest, handler, max_retries=3)
    with pytest.raises(ApiError) as exc:
        _run_capturing(ctx, op, {}, None)
    assert calls["n"] == 1  # not retried
    assert exc.value.classification == "upstream_error"
    assert exc.value.retryable is False


def test_taxonomy_upstream_500_retried_then_succeeds(manifest: Manifest) -> None:
    """A generic 500 (no policy override) is retried with bounded backoff by the
    SDK transport, then succeeds."""
    op = manifest.get("sell_finances.getTransactionSummary")  # read, no policy
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={"errors": [{"message": "boom"}]})
        return httpx.Response(200, json={"transactionSummaries": []})

    ctx = _ctx(manifest, handler, max_retries=3)
    out = _run_capturing(ctx, op, {}, None)
    assert calls["n"] == 3  # SDK retried twice, then succeeded
    assert json.loads(out) == {"transactionSummaries": []}


def test_capabilities_command_describe_leads(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["capabilities", "describe",
                                 "sell_leads.getAllClassifiedLeads", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["availability"] == "limited_release"
    assert payload["production_approval"] == "eBay business unit (Limited Release)"
    assert payload["retry_on_failure"] is False


def test_capabilities_command_list_unavailable(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["capabilities", "list", "--status", "unavailable",
                                 "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    keys = {c["operation"] for c in payload["capabilities"]}
    assert "sell_leads.getAllClassifiedLeads" in keys
    assert "commerce_vero.getVeroReport" in keys
    # Available single-item Browse is excluded by the unavailable filter.
    assert "buy_browse.getItem" not in keys


def test_capabilities_describe_awaiting_feedback_upstream(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["capabilities", "describe",
                                 "commerce_feedback.getItemsAwaitingFeedback",
                                 "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["availability"] == "upstream_failure"
    assert payload["fallback"] == "trading.GetItemsAwaitingFeedback"
    assert payload["retry_on_failure"] is True


def test_auth_doctor_show_capabilities(runner: CliRunner) -> None:
    """--show-capabilities adds the policy snapshot to the doctor report."""
    result = runner.invoke(cli, ["auth", "doctor", "--show-capabilities", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "capabilities" in payload
    ops = {c["operation"] for c in payload["capabilities"]["capabilities"]}
    assert "sell_compliance.getListingViolations" in ops  # stale


def test_error_json_includes_classification(manifest: Manifest) -> None:
    """The structured error output surfaces the stable classification."""

    op = manifest.get("sell_leads.getAllClassifiedLeads")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": [{"message": "Access is denied"}]})

    ctx = _ctx(manifest, handler)
    with pytest.raises(ApiError) as exc:
        _run_capturing(ctx, op, {}, None)
    err = exc.value
    assert err.classification == "capability_not_granted"
    as_dict = err.as_dict()["error"]
    assert as_dict["classification"] == "capability_not_granted"
    assert as_dict["retryable"] is False


# ---------------------------------------------------------------------------
# F6 — test-run execute plan + idempotent cleanup
# ---------------------------------------------------------------------------

def test_f6_execute_plan_only(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(cli, ["sell", "inventory", "test-run", "execute",
                            "--run-id", "plan-run", "--source-sku", "S1",
                            "--test-sku", "AAAAA", "--plan-only",
                            "--ledger-dir", str(tmp_path), "--format", "json"],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    plan = json.loads(r.output)
    assert plan["run_id"] == "plan-run"
    assert plan["source_skus"] == ["S1"]
    assert plan["will_cleanup"] is False


def test_f6_execute_cleanup_requires_allow_write(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(cli, ["sell", "inventory", "test-run", "execute",
                            "--run-id", "cw", "--cleanup",
                            "--ledger-dir", str(tmp_path), "--format", "json"])
    assert r.exit_code != 0
    assert "--allow-write" in (r.output + str(r.exception))


def test_f6_execute_cleanup_is_idempotent(manifest: Manifest, tmp_path: Path) -> None:
    """A second execute --cleanup is a no-op (404s count as already-clean)."""
    from bidkit_cli.ledger import RunLedger, save_ledger

    ledger = RunLedger(run_id="idem", created_at="t",
                       test_skus=["AAAAA"], offer_ids=["O1"], listing_ids=["L1"])
    save_ledger(ledger, base_dir=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        # Everything is already gone: withdraw/delete return 404, Browse 404.
        if "/item/" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    from bidkit import EbayClient, EbayConfig
    mock = EbayClient(EbayConfig(access_token="t", marketplace_id="EBAY_DE"),
                      http_client=client)
    runner = CliRunner()
    with patch.object(CliContext, "client", new=property(lambda self: mock)):
        r = runner.invoke(cli, [
            "sell", "inventory", "test-run", "execute", "--run-id", "idem",
            "--cleanup", "--allow-write", "--yes",
            "--ledger-dir", str(tmp_path), "--wait", "0", "--format", "json",
        ], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    report = json.loads(r.output)
    assert report["seller_records_deleted"] is True
    assert report["frontend_converged"] is True


# ---------------------------------------------------------------------------
# F8/F13 — executable examples for conditionally-required search params
# ---------------------------------------------------------------------------

def test_f13_browse_search_example_includes_q(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "examples", "buy_browse.search", "--format", "text"])
    assert result.exit_code == 0, result.output
    assert "--q VALUE" in result.output
    assert "--limit 30" in result.output


def test_f13_feed_tasks_example_includes_date_range(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "examples", "sell_feed.getTasks", "--format", "text"])
    assert result.exit_code == 0, result.output
    assert "--date-range" in result.output
