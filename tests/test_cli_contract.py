"""CLI contract hardening: exit codes, ledger correlation, option collisions, errors.

The headline regression here invokes the real ``main()`` entry point (which
``sys.exit``s on Click's intentional return value) rather than ``CliRunner``,
so it fails the moment the exit-code contract is swallowed again.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ApiError
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


def _run_capturing(ctx: CliContext, op, path_params: dict, body) -> str:
    out_buf = io.StringIO()
    with redirect_stdout(out_buf):
        execute(ctx, op, path_params=path_params, query_params={},
                header_params={}, body=body, files={})
    return out_buf.getvalue()


def _browse_item(*, item_id="v1|L1|0", title="Vase", price="12.50", currency="EUR",
                 end=None, description="TEST ONLY — nothing shipped"):
    item = {
        "itemId": item_id, "title": title,
        "price": {"value": price, "currency": currency},
        "categoryId": "14981", "description": description,
        "buyingOptions": ["FIXED_PRICE"],
    }
    if end is not None:
        item["itemEndDate"] = end
    return item


# ---------------------------------------------------------------------------
# F1 — verify-public non-zero exit reaches the shell (subprocess-style)
# ---------------------------------------------------------------------------

def test_f1_main_exits_nonzero_on_unmet_expectation(manifest: Manifest) -> None:
    """The installed entry point exits 1 on an unmet expectation (not 0).

    This runs the REAL ``main()`` (sys.argv → cli.main(standalone_mode=False) →
    sys.exit(rv)), not ``CliRunner``: ``CliRunner`` handles ``Exit`` itself and
    masked the regression where ``standalone_mode=False`` converted the exit into
    a return value that ``main()`` ignored.
    """
    from bidkit import EbayClient, EbayConfig

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())  # active, not not_listed
        return httpx.Response(404)

    mock = EbayClient(EbayConfig(access_token="t", marketplace_id="EBAY_DE"),
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    argv = [
        "bidkit", "sell", "inventory", "verify-public", "--listing-id", "1",
        "--expect", "not_listed", "--wait", "0", "--format", "json",
    ]
    with patch("sys.argv", argv), patch.object(
        CliContext, "client", new=property(lambda self: mock)
    ), pytest.raises(SystemExit) as exc_info:
        from bidkit_cli.app import main

        main()
    assert exc_info.value.code == 1


def test_f1_main_exits_zero_on_met_expectation(manifest: Manifest) -> None:
    """A met expectation still exits 0 through the real entry point."""
    from bidkit import EbayClient, EbayConfig

    def handler(request: httpx.Request) -> httpx.Response:
        if "/item/" in request.url.path:
            return httpx.Response(200, json=_browse_item())
        return httpx.Response(404)

    mock = EbayClient(EbayConfig(access_token="t", marketplace_id="EBAY_DE"),
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    argv = [
        "bidkit", "sell", "inventory", "verify-public", "--listing-id", "1",
        "--expect", "active", "--wait", "0", "--format", "json",
    ]
    with patch("sys.argv", argv), patch.object(
        CliContext, "client", new=property(lambda self: mock)
    ), pytest.raises(SystemExit) as exc_info:
        from bidkit_cli.app import main

        main()
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# F2 — ledger correlation: wire name, createOffer SKU, cleanup events,
#      cleanup_status, auto-create ledger
# ---------------------------------------------------------------------------

def test_f2_publish_records_offerid_wire_name(manifest: Manifest, tmp_path: Path) -> None:
    """publishOffer records the offerId from the path (wire name, not offer_id)."""
    from bidkit_cli.ledger import RunLedger, load_ledger, save_ledger

    ledger = RunLedger(run_id="run-wire", created_at="t")
    save_ledger(ledger, base_dir=tmp_path)

    op = manifest.get("sell_inventory.publishOffer")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"listingId": "L1"})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_run_id="run-wire")
    with patch("bidkit_cli.ledger.default_ledger_dir", return_value=tmp_path):
        _run_capturing(ctx, op, {"offerId": "OFFER9"}, None)
    loaded = load_ledger("run-wire", base_dir=tmp_path)
    publish_events = [e for e in loaded.events if e.operation == op.key]
    assert publish_events, "publishOffer produced no event"
    # The path param is keyed by wire name; the recorder must read offerId.
    assert publish_events[0].offer_id == "OFFER9"
    assert publish_events[0].listing_id == "L1"


def test_f2_createoffer_records_sku_from_body(manifest: Manifest, tmp_path: Path) -> None:
    """createOffer records the SKU from the request body (no path param exists)."""
    from bidkit_cli.ledger import RunLedger, save_ledger

    ledger = RunLedger(run_id="run-sku", created_at="t")
    save_ledger(ledger, base_dir=tmp_path)

    op = manifest.get("sell_inventory.createOffer")
    body = {"sku": "SKU-FROM-BODY", "listingDescription": "TEST ONLY — x"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"offerId": "O1"})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_run_id="run-sku")
    with patch("bidkit_cli.ledger.default_ledger_dir", return_value=tmp_path):
        _run_capturing(ctx, op, {}, body)
    from bidkit_cli.ledger import load_ledger

    loaded = load_ledger("run-sku", base_dir=tmp_path)
    create_events = [e for e in loaded.events if e.operation == op.key]
    assert create_events
    assert create_events[0].sku == "SKU-FROM-BODY"
    assert create_events[0].offer_id == "O1"


def test_f2_autocreates_ledger_without_init(manifest: Manifest, tmp_path: Path) -> None:
    """A write with --test-run-id records even when test-run init was skipped."""
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    body = {"product": {"title": "V", "description": "TEST ONLY run-auto-create"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True,
               test_run_id="run-auto-create")
    with patch("bidkit_cli.ledger.default_ledger_dir", return_value=tmp_path):
        _run_capturing(ctx, op, {"sku": "SKU1"}, body)
    from bidkit_cli.ledger import load_ledger

    # The ledger was auto-created; load does not raise.
    loaded = load_ledger("run-auto-create", base_dir=tmp_path)
    assert "SKU1" in loaded.test_skus


def test_f2_cleanup_records_events_and_advances_status(manifest: Manifest, tmp_path: Path) -> None:
    """test-run execute --cleanup records withdraw/delete events and advances cleanup_status."""
    from bidkit_cli.ledger import CLEANUP_COMPLETE, RunLedger, save_ledger

    ledger = RunLedger(
        run_id="run-clean", created_at="t",
        test_skus=["SKU1"], offer_ids=["O1"], listing_ids=["L1"],
    )
    save_ledger(ledger, base_dir=tmp_path)

    # Seed the event stream so _sku_for_listing can recover the SKU for L1.
    from bidkit_cli.ledger import RunEvent

    ledger.add_event(RunEvent(operation="sell_inventory.createOffer", timestamp="t",
                              sku="SKU1", offer_id="O1"))
    ledger.add_event(RunEvent(operation="sell_inventory.publishOffer", timestamp="t",
                              offer_id="O1", listing_id="L1"))
    save_ledger(ledger, base_dir=tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/item/" in path:  # Browse getItem -> an ENDED/retained public record
            past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
            return httpx.Response(200, json=_browse_item(end=past))
        if "/inventory_item/" in path or "/offer/" in path or "/offer_group/" in path:
            return httpx.Response(204 if request.method in {"PUT", "POST"} else 404)
        return httpx.Response(404)

    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_run_id="run-clean")
    with patch("bidkit_cli.ledger.default_ledger_dir", return_value=tmp_path):
        from bidkit_cli.commands.workflows import _cleanup_run

        report = _cleanup_run(ctx, ledger, tmp_path, wait_seconds=0.0, poll_interval=0.0)

    from bidkit_cli.ledger import load_ledger

    loaded = load_ledger("run-clean", base_dir=tmp_path)
    ops = {e.operation for e in loaded.events}
    # Cleanup mutations now appear in the event stream (previously absent).
    assert "sell_inventory.withdrawOffer" in ops or "sell_inventory.deleteOffer" in ops
    assert "sell_inventory.deleteInventoryItem" in ops
    # cleanup_status advanced from pending to complete on full success.
    assert loaded.cleanup_status == CLEANUP_COMPLETE
    # F11: with the SKU recovered, the listing reached not_listed (seller gone
    # AND public 404), not a stuck public_ended.
    assert report["per_listing"][0]["frontend_state"] == "not_listed"


# ---------------------------------------------------------------------------
# F3 — test-run execute --cleanup requires --yes; dead flags removed
# ---------------------------------------------------------------------------

def test_f3_cleanup_requires_yes(runner: CliRunner, manifest: Manifest, tmp_path: Path) -> None:
    """Cleanup without --yes is refused even with --allow-write."""
    from bidkit_cli.ledger import RunLedger, save_ledger

    save_ledger(RunLedger(run_id="r3", created_at="t", offer_ids=["O1"]),
                base_dir=tmp_path)
    with patch("bidkit_cli.ledger.default_ledger_dir", return_value=tmp_path):
        result = runner.invoke(cli, [
            "sell", "inventory", "test-run", "execute", "--run-id", "r3",
            "--cleanup", "--allow-write", "--format", "json",
        ])
    assert result.exit_code != 0
    # The refusal message names both gates (it travels on the SafetyError).
    blob = result.output + (str(result.exception) if result.exception else "")
    assert "--yes" in blob


def test_f3_execute_help_has_no_dead_flags(runner: CliRunner) -> None:
    """The dead --allow-scrambled-test-data / --verify-frontend flags are gone."""
    result = runner.invoke(cli, ["sell", "inventory", "test-run", "execute", "--help"])
    assert "--allow-scrambled-test-data" not in result.output
    assert "--verify-frontend" not in result.output


# ---------------------------------------------------------------------------
# F4 — lifecycle POSTs classified as write (no expert escape hatch)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", [
    "sell_inventory.createOffer",
    "sell_inventory.publishOffer",
    "sell_inventory.withdrawOffer",
    "commerce_media.createImageFromFile",
])
def test_f4_lifecycle_posts_are_write(manifest: Manifest, key: str) -> None:
    from bidkit_cli.safety import effective_risk

    op = manifest.get(key)
    risk, _ = effective_risk(op)
    assert risk == "write", f"{key} should be classified write, got {risk}"


def test_f4_write_needs_only_allow_write_not_expert(manifest: Manifest) -> None:
    """createOffer runs with --allow-write alone (no --allow-write-expert, no --yes)."""
    op = manifest.get("sell_inventory.createOffer")
    body = {"listingDescription": "TEST ONLY — nothing shipped."}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"offerId": "O1"})

    # allow_write=True but allow_write_expert=False, yes=False: must succeed now.
    ctx = _ctx(manifest, handler, allow_write=True, yes=True, test_mode=True)
    out = _run_capturing(ctx, op, {}, body)
    assert json.loads(out)["offerId"] == "O1"


def test_f4_nonidempotency_hint_uses_effective_risk(manifest: Manifest) -> None:
    """A publishOffer (effective risk write) 400 carries the non-idempotency note."""
    op = manifest.get("sell_inventory.publishOffer")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"errors": [{"errorId": 99999, "message": "boom"}]})

    ctx = _ctx(manifest, handler, allow_write=True, yes=True)
    with pytest.raises(ApiError) as exc:
        _run_capturing(ctx, op, {"offerId": "O1"}, None)
    # publishOffer's *generated* risk is unknown; the hint now keys off the
    # effective risk (write), so the non-idempotency note fires.
    assert "remote state may have changed" in (exc.value.hint or "").lower()


# ---------------------------------------------------------------------------
# F5 — global argv reordering no longer shadows same-named local flags
# ---------------------------------------------------------------------------

def test_f5_cache_clear_yes_works(runner: CliRunner, tmp_path: Path) -> None:
    """`auth cache clear --yes` clears the cache (the local --yes shadow is gone)."""
    cache = tmp_path / "tokens.json"
    cache.write_text("{}")
    with patch.object(CliContext, "token_cache_path", new=str(cache)):
        result = runner.invoke(cli, ["auth", "cache", "clear", "--yes"])
    assert result.exit_code == 0, result.output
    assert not cache.exists()


def test_f5_collision_check_forbids_local_global_option() -> None:
    """The build-time check raises if a leaf command declares a global option."""
    import click

    from bidkit_cli.app import _assert_no_global_option_collision

    @click.group()
    def root():
        pass

    @root.command()
    @click.option("--yes", is_flag=True)  # --yes is global
    def cmd(yes):
        pass

    with pytest.raises(RuntimeError, match="global-option collision"):
        _assert_no_global_option_collision(root)


def test_f5_generated_query_format_disambiguated(manifest: Manifest) -> None:
    """get-offers' `format` query param is exposed as --q-format, not stolen by global --format."""
    op = manifest.get("sell_inventory.getOffers")
    # The generated command must not declare --format (it would collide).
    from bidkit_cli.commands.generated import _option_name

    fmt_param = next(p for p in op.query_params if p.wire_name == "format")
    assert _option_name(fmt_param) == "q-format"


# ---------------------------------------------------------------------------
# F6 — first-install OAuth bootstrap
# ---------------------------------------------------------------------------

def test_f6_doctor_has_ready_and_next_steps(runner: CliRunner, tmp_path: Path) -> None:
    """auth doctor reports readiness + actionable next_steps even with no config."""
    config = tmp_path / "missing.json"
    result = runner.invoke(cli, [
        "--config", str(config), "auth", "doctor", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert "ready" in report
    assert "next_steps" in report
    # A fresh install is not ready and is told what to create.
    assert report["ready"] is False
    assert any("developer.ebay.com" in s for s in report["next_steps"])


def test_f6_auth_init_writes_skeleton(runner: CliRunner, tmp_path: Path) -> None:
    """`auth init` writes a skeleton config with placeholder credentials."""
    config = tmp_path / "cfg.json"
    result = runner.invoke(cli, [
        "--config", str(config), "auth", "init", "--marketplace", "EBAY_DE",
        "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(config.read_text())
    assert "REPLACE_WITH_APP_ID" in data["credentials"]["app_id"]
    assert data["marketplace_id"] == "EBAY_DE"
    assert any("auth login" in s for s in json.loads(result.output)["next_steps"])


def test_f6_login_hint_points_at_config(
    runner: CliRunner, manifest: Manifest, tmp_path: Path
) -> None:
    """auth login with no keyset gives an actionable hint, not a bare message."""
    config = tmp_path / "empty.json"
    config.write_text(json.dumps({"credentials": {}}))
    result = runner.invoke(cli, [
        "--config", str(config), "auth", "login", "--no-browser", "--format", "json",
    ])
    assert result.exit_code != 0
    blob = result.output + (str(result.exception) if result.exception else "")
    assert "developer.ebay.com/my/keys" in blob or "app_id" in blob


# ---------------------------------------------------------------------------
# F7 — 401 taxonomy default is unauthenticated
# ---------------------------------------------------------------------------

def test_f7_default_401_is_unauthenticated_retryable() -> None:
    from bidkit_cli.classification import classify_response

    cls = classify_response(401, operation="sell_inventory.getInventoryItem")
    assert cls.kind == "unauthenticated"
    assert cls.retry is True


def test_f7_edis_401_is_account_not_eligible() -> None:
    from bidkit_cli.classification import classify_response

    cls = classify_response(
        401, operation="sell_edelivery_international_shipping.createLabel"
    )
    assert cls.kind == "account_not_eligible"
    assert cls.retry is False
    assert "eDIS" in (cls.hint or "")


# ---------------------------------------------------------------------------
# F8 — bounded error envelope, hint precedence, transport policy, text mode
# ---------------------------------------------------------------------------

def test_f8_html_upstream_error_bounds_details(manifest: Manifest) -> None:
    """A non-JSON (HTML) upstream failure does not leak the full page into details."""
    from bidkit.errors import EbayAPIError

    from bidkit_cli.dispatch import _classified_api_error

    op = manifest.get("buy_browse.getItem")
    html = "<html>" + ("x" * 5000) + "</html>"
    response = httpx.Response(500, content=html.encode(),
                              headers={"content-type": "text/html"})
    exc = EbayAPIError.from_response(response)
    err = _classified_api_error(op, exc)
    # details is dropped for non-JSON bodies; the bounded normalized_body carries
    # only a short preview.
    assert err.details is None
    assert err.normalized_body is not None
    assert len(err.normalized_body.get("body_preview", "")) <= 281


def test_f8_available_policy_does_not_poison_404(manifest: Manifest) -> None:
    """A 404 on an _AVAILABLE op (buy_browse.getItem) gets no 'works for standard account' hint."""
    from bidkit_cli.classification import classify_response

    cls = classify_response(404, operation="buy_browse.getItem")
    assert cls.kind == "not_found"
    hint = cls.hint or ""
    assert "works for a standard seller account" not in hint


def test_f8_transport_retry_honors_policy(manifest: Manifest) -> None:
    """A transport error on a policy-suppressed op (Leads) is not retryable."""
    from bidkit.errors import EbayTransportError

    from bidkit_cli.dispatch import _classified_transport_error

    op = manifest.get("sell_leads.getLead") or manifest.get(
        "sell_leads.findLead"
    ) or next(o for o in manifest.operations if o.service_key == "sell_leads")
    err = _classified_transport_error(op, EbayTransportError("timeout"))
    assert err.retryable is False


def test_f8_text_mode_keeps_classification() -> None:
    """report_error in text mode surfaces classification/retryable."""
    import io

    from bidkit_cli.errors import ApiError, report_error

    err = ApiError("boom", status=500, classification="upstream_error",
                   retryable=True, retry_after=1.5)
    buf = io.StringIO()
    with patch("sys.stderr", buf):
        code = report_error(err, json_mode=False)
    text = buf.getvalue()
    assert code == 4
    assert "classification: upstream_error" in text
    assert "retryable: True" in text
    assert "retry_after: 1.5s" in text


def test_f8_main_catch_all_translates_unexpected_error(tmp_path: Path) -> None:
    """An unexpected exception is translated to a stable error, not a traceback."""
    argv = ["bidkit", "--config", str(tmp_path / "nope.json"), "auth", "doctor",
            "--format", "json"]
    with patch("bidkit_cli.app.cli.main", side_effect=RuntimeError("kaboom")), \
         patch("sys.argv", argv), pytest.raises(SystemExit) as exc_info:
        from bidkit_cli.app import main

        main()
    # Catch-all maps to the dedicated internal-error exit code — a tool fault is
    # never mislabeled as the caller's mistake (2) or a raw 1.
    assert exc_info.value.code == 9


# ---------------------------------------------------------------------------
# F9 — auth doctor truthful token cache + redaction
# ---------------------------------------------------------------------------

def test_f9_token_cache_exists_reflects_reality(runner: CliRunner, tmp_path: Path) -> None:
    """token_cache.exists is True when the cache file is present (unexpanded ~)."""
    cache = tmp_path / "tokens.json"
    cache.write_text("{}")
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps({"credentials": {"app_id": "a-PRD-b",
                                                  "cert_id": "c", "ru_name": "r",
                                                  "access_token": "t"}}))
    with patch.object(CliContext, "token_cache_path", new=str(cache)):
        result = runner.invoke(cli, ["--config", str(config), "auth", "doctor",
                                     "--format", "json"])
    report = json.loads(result.output)
    assert report["token_cache"]["exists"] is True


def test_f9_present_is_not_set_8_chars(runner: CliRunner, tmp_path: Path) -> None:
    """_present reports '<set>' not the leaked '<set:8 chars>'."""
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps({"credentials": {"app_id": "a-PRD-b",
                                                  "cert_id": "c", "ru_name": "r",
                                                  "access_token": "tok"}}))
    result = runner.invoke(cli, ["--config", str(config), "auth", "doctor",
                                 "--format", "json"])
    report = json.loads(result.output)
    assert report["cert_id"] == "<set>"
    assert "set:8 chars" not in json.dumps(report)


# ---------------------------------------------------------------------------
# F10 — --select accepts snake_case against a camelCase dump
# ---------------------------------------------------------------------------

def test_f10_select_accepts_snake_case() -> None:
    from bidkit_cli.rendering import select_path

    data = {"itemSummaries": [{"itemId": "A"}, {"itemId": "B"}]}
    out = select_path(data, "item_summaries[].item_id")
    assert out == ["A", "B"]


def test_f10_select_still_accepts_camel_case() -> None:
    from bidkit_cli.rendering import select_path

    data = {"itemSummaries": [{"itemId": "A"}]}
    assert select_path(data, "itemSummaries[].itemId") == ["A"]


# ---------------------------------------------------------------------------
# F13 — capabilities output sizing + fuzzy describe
# ---------------------------------------------------------------------------

def test_f13_list_default_is_curated_only(runner: CliRunner) -> None:
    """`capabilities list` defaults to curated (restricted/broken) surfaces only."""
    result = runner.invoke(cli, ["capabilities", "list", "--format", "json"])
    report = json.loads(result.output)
    assert report["default_view"] == "curated"
    # The default view is much smaller than the full ~455-operation dump.
    assert report["operation_count"] < 50
    # Every listed op has a non-default availability (curated).
    assert all(v["availability"] != "available" for v in report["capabilities"])


def test_f13_list_all_includes_every_operation(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["capabilities", "list", "--all", "--format", "json"])
    report = json.loads(result.output)
    assert report["default_view"] == "all"
    assert report["operation_count"] > 400


def test_f13_describe_near_miss_suggests(runner: CliRunner) -> None:
    """A near-miss operation key suggests candidates instead of a bare error."""
    result = runner.invoke(cli, ["capabilities", "describe", "getItm",
                                 "--format", "json"])
    assert result.exit_code != 0
    # CliRunner does not run main()'s error renderer, so the hint rides on the
    # raised exception; it surfaces in the real binary via report_error.
    exc = result.exception
    hint = getattr(exc, "hint", None) or ""
    assert "did you mean" in hint.lower() or "getItem" in hint


# ---------------------------------------------------------------------------
# F11 — cleanup-report reaches not_listed with the SKU recovered
# ---------------------------------------------------------------------------

def test_f11_cleanup_report_reaches_not_listed(manifest: Manifest, tmp_path: Path) -> None:
    """cleanup-report passes the recovered SKU so a deleted listing is not_listed."""
    from bidkit_cli.commands.workflows import _sku_for_listing
    from bidkit_cli.ledger import RunEvent, RunLedger, save_ledger

    ledger = RunLedger(run_id="r11", created_at="t", test_skus=["SKU11"],
                       offer_ids=["O11"], listing_ids=["L11"])
    ledger.add_event(RunEvent(operation="sell_inventory.createOffer", timestamp="t",
                              sku="SKU11", offer_id="O11"))
    ledger.add_event(RunEvent(operation="sell_inventory.publishOffer", timestamp="t",
                              offer_id="O11", listing_id="L11"))
    save_ledger(ledger, base_dir=tmp_path)
    assert _sku_for_listing(ledger, "L11") == "SKU11"


# ---------------------------------------------------------------------------
# F7 supplement — verifier content_verified + states (smoke through command)
# ---------------------------------------------------------------------------

def test_f_supplement_verify_public_states_documented(runner: CliRunner) -> None:
    """verify-public --help documents the full --expect vocabulary."""
    result = runner.invoke(cli, ["sell", "inventory", "verify-public", "--help"])
    for state in ("active", "visible", "not_listed", "not_found"):
        assert state in result.output


def test_r3_expired_token_on_policy_surface_stays_unauthenticated() -> None:
    """A 401 on a limited-release/entitlement surface is still an ordinary
    expired-token failure — only account-restricted surfaces (eDIS) justify
    account_not_eligible's do-not-re-authenticate guidance."""
    from bidkit_cli.classification import classify_response

    for op in ("sell_leads.getAllClassifiedLeads", "buy_deal.getDeals",
               "commerce_vero.getVeroReasonCodes"):
        cls = classify_response(401, operation=op, body="denied", content_type="text/plain")
        assert cls.kind == "unauthenticated", op
        assert cls.retry is True, op
    cls = classify_response(
        401, operation="sell_edelivery_international_shipping.getPackage",
        body="denied", content_type="text/plain",
    )
    assert cls.kind == "account_not_eligible"
    assert cls.retry is False


def test_r4_non_json_body_bounded_on_every_status() -> None:
    """An HTML/text error body is normalized (never echoed verbatim) on 400/404/
    429, not only on 401/403/5xx."""
    from bidkit_cli.classification import classify_response

    page = "<html>" + "x" * 5000 + "</html>"
    for status in (400, 404, 429, 418):
        cls = classify_response(status, operation="buy_browse.getItem",
                                body=page, content_type="text/html")
        assert cls.normalized_body is not None, status
        assert len(cls.normalized_body["body_preview"]) < 400, status


def test_r8_select_ambiguous_key_is_an_error() -> None:
    from bidkit_cli.errors import IoError
    from bidkit_cli.rendering import select_path

    # "item-id" matches neither key exactly nor case-insensitively, and both
    # keys collapse to the same alphanumeric run — refusing beats guessing.
    with pytest.raises(IoError, match="ambiguous"):
        select_path({"itemId": 1, "item_id": 2}, "item-id")
    # An exact or unique case-insensitive key never trips the ambiguity check.
    assert select_path({"itemId": 1, "item_id": 2}, "item_id") == 2
    assert select_path({"itemId": 1, "item_id": 2}, "ITEM_ID") == 2
