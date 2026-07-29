"""Stateful workflow commands layered above the generated operations.

These are hand-written Click commands that compose generated operations into
intent-level workflows the raw OAS surface cannot express:

* ``sell inventory verify-public``: poll the public/Browse representation of a
  listing with explicit stale-after-delete semantics and field-level
  assertions, so an agent can distinguish "delete failed" from "delete
  succeeded, public state stale".
* ``buy purchases capability``: a capability diagnostic that honestly reports
  member-purchase history is unavailable on the current OAS surface, instead of
  letting an agent infer "no purchases" from a logged-out page or mistake seller
  orders for purchases.

The commands are injected into the generated command tree (namespace → service)
in :func:`inject_workflow_commands`, so the natural path an agent guesses
(``bidkit sell inventory verify-public``) works.
"""

from __future__ import annotations

import contextlib
from datetime import UTC
from typing import Any

import click
import httpx2

from ..context import CliContext
from ..errors import SafetyError
from ..rendering import emit_json
from ..workflows import FRONTEND_STATES, verify_public
from .options import public_poll_options


def inject_workflow_commands(namespace_groups: list[click.Group]) -> list[click.Group]:
    """Attach workflow commands to the generated namespace/service groups.

    Returns the same list (mutated in place) so :func:`build_cli` can keep its
    flat ``for group in build_generated_groups(...)`` loop. Missing target
    groups are skipped silently: a future manifest that drops ``sell.inventory``
    or ``buy`` must not crash startup, only lose the convenience command.
    """
    _inject_sell_inventory_verify_public(namespace_groups)
    _inject_sell_inventory_test_run(namespace_groups)
    _inject_buy_purchases(namespace_groups)
    return namespace_groups


# ---------------------------------------------------------------------------
# sell inventory verify-public
# ---------------------------------------------------------------------------

_VERIFY_PUBLIC_HELP = (
    "Verify the PUBLIC/Browse representation of a listing. Browse getItem is "
    "always called with the RESTful id v1|<legacy>|0, so a numeric "
    "--listing-id is normalized automatically (no more false 404s). HTTP 403 is "
    "never treated as proof the item is absent. Pass --sku to also read the "
    "seller-side state so the report can name 'not_listed' (seller deleted + "
    "public ended) vs 'stale_after_delete' (public still active-looking). "
    "--expect choices: active (purchasable), visible (any public record incl. "
    "retained history), not_listed (seller deleted + public ended), not_found "
    "(Browse 404). Exits non-zero when the expectation is not met. The output is "
    "a bounded, privacy-safe projection by default; pass --full to retain the "
    "raw Browse body for expert use."
)


def _inject_sell_inventory_verify_public(namespace_groups: list[click.Group]) -> None:
    sell = _find_group(namespace_groups, "sell")
    if sell is None:
        return
    inventory = _find_group(sell.commands.values(), "inventory")
    if inventory is None:
        return
    inventory.add_command(_verify_public_command())  # type: ignore[arg-type]


def _verify_public_command() -> click.Command:
    @click.command(
        "verify-public",
        help=_VERIFY_PUBLIC_HELP,
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    @click.option("--listing-id", required=True, help="The public listing/item id to verify.")
    @click.option("--sku", default=None,
                  help="Inventory SKU backing the listing; enables seller-side state.")
    @click.option("--expect", "expect_browse",
                  type=click.Choice(["active", "visible", "not_listed", "not_found"]),
                  default="visible",
                  help="Expected public state: active (purchasable), visible (any public "
                       "representation incl. retained history), not_listed (seller deleted "
                       "and public ended/unpurchasable), or not_found (Browse 404).")
    @click.option("--expect-title", default=None, help="Assert the public title matches exactly.")
    @click.option("--expect-description-contains", default=None,
                  help="Assert the public description contains this marker (e.g. 'TEST ONLY').")
    @click.option("--expect-image-count", type=click.IntRange(min=0), default=None,
                  help="Assert the public image count (primary + additional).")
    @click.option("--expect-price", default=None,
                  help="Assert the public price value (e.g. 12.50).")
    @click.option("--expect-currency", default=None,
                  help="Assert the public price currency (e.g. EUR).")
    @click.option("--expect-category-id", default=None, help="Assert the public category id.")
    @click.option("--expect-buying-option", default=None,
                  help="Assert a buying option is present (e.g. FIXED_PRICE).")
    @public_poll_options()
    @click.option("--full", is_flag=True, default=False,
                  help="Retain the full Browse response body (default: a bounded, "
                       "privacy-safe projection). Expert use; the legal/contact blob is large.")
    @click.pass_context
    def _cmd(ctx: click.Context, **kwargs: Any) -> None:
        context: CliContext = ctx.obj
        if context.dry_run:
            from ..workflows import normalize_item_id
            browse_id, legacy_id = normalize_item_id(kwargs["listing_id"])
            preview = {
                "dry_run": True,
                "workflow": "sell_inventory.verify_public",
                "listing_id": kwargs["listing_id"],
                "legacy_item_id": legacy_id,
                "browse_item_id": browse_id,
                "sku": kwargs.get("sku"),
                "expect": kwargs["expect_browse"],
                "full": kwargs.get("full", False),
                "primary_check": "buy_browse.getItem",
                "seller_check": "sell_inventory.getInventoryItem" if kwargs.get("sku") else None,
                "assertions": [k for k, v in kwargs.items()
                               if k.startswith("expect_") and k != "expect_browse"
                               and v is not None],
                "wait_seconds": kwargs["wait_seconds"],
                "poll_interval": kwargs["poll_interval"],
                "note": (
                    "Browse getItem is called with the RESTful id "
                    "v1|<legacy>|0 (a numeric --listing-id is normalized). "
                    "HTTP 403 is never proof of absence. Exits non-zero when "
                    "the expectation is not met."
                ),
            }
            emit_json(preview, pretty=context.pretty)
            return
        report = verify_public(
            context,
            listing_id=kwargs["listing_id"],
            sku=kwargs.get("sku"),
            expect_browse=kwargs["expect_browse"],
            expect_title=kwargs.get("expect_title"),
            expect_description_contains=kwargs.get("expect_description_contains"),
            expect_image_count=kwargs.get("expect_image_count"),
            expect_price=kwargs.get("expect_price"),
            expect_currency=kwargs.get("expect_currency"),
            expect_category_id=kwargs.get("expect_category_id"),
            expect_buying_option=kwargs.get("expect_buying_option"),
            wait_seconds=kwargs["wait_seconds"],
            poll_interval=kwargs["poll_interval"],
            full=kwargs.get("full", False),
        )
        emit_json(report, pretty=context.pretty)
        # This is an assertion/CI-style verifier. Exit non-zero when the
        # requested expectation was not met (including a timeout) so a script
        # can branch on it; the full JSON report still goes to stdout. A
        # transport/API failure raises before reaching here and keeps its own
        # exit code. An unmet expectation is information rendered as a report,
        # not a malformed request, so we use a dedicated exit code (1).
        if not report.get("met_expectation"):
            ctx.exit(1)

    return _cmd


# ---------------------------------------------------------------------------
# sell inventory test-run ledger
# ---------------------------------------------------------------------------

_TEST_RUN_HELP = (
    "Manage a durable test-run ledger: record the SKUs, offers, listings, and "
    "trace ids a controlled test creates, then produce a cleanup report that "
    "distinguishes seller-records-deleted, frontend-converged, and "
    "financially-reversible (always false: deleting a record cannot reverse a "
    "fee eBay has already booked)."
)


def _inject_sell_inventory_test_run(namespace_groups: list[click.Group]) -> None:
    sell = _find_group(namespace_groups, "sell")
    if sell is None:
        return
    inventory = _find_group(sell.commands.values(), "inventory")
    if inventory is None:
        return
    if "test-run" in inventory.commands:
        return
    group = click.Group("test-run", help=_TEST_RUN_HELP)
    group.add_command(_test_run_init_command())
    group.add_command(_test_run_record_command())
    group.add_command(_test_run_show_command())
    group.add_command(_test_run_execute_command())
    group.add_command(_test_run_cleanup_report_command())
    inventory.add_command(group)


def _ledger_base_dir(context: CliContext) -> Any:
    """The shared ledger directory (global ``--ledger-dir`` or the default).

    The same resolution dispatch's auto-recorder uses, so the test-run commands
    and automatic event recording always read and write one ledger per run.
    """
    from ..dispatch import _ledger_base_dir as resolve

    return resolve(context)


def _test_run_init_command() -> click.Command:
    from datetime import datetime

    from ..ledger import RunLedger, new_run_id, save_ledger

    @click.command("init", help="Create a new test-run ledger and print its run id.")
    @click.option("--run-id", default=None, help="Explicit run id (default: generated).")
    @click.option("--source-sku", "source_skus", multiple=True,
                  help="Real source SKU cross-wired into the test (repeatable).")
    @click.option("--note", multiple=True, help="Free-form note (repeatable).")
    @click.pass_context
    def _cmd(ctx, run_id, source_skus, note):
        context: CliContext = ctx.obj
        base = _ledger_base_dir(context)
        rid = run_id or new_run_id()
        ledger = RunLedger(
            run_id=rid,
            created_at=datetime.now(UTC).isoformat(),
            source_skus=list(source_skus),
            notes=list(note),
        )
        path = save_ledger(ledger, base_dir=base)
        emit_json({"run_id": rid, "ledger_file": str(path), "created_at": ledger.created_at},
                  pretty=context.pretty)

    return _cmd


def _test_run_record_command() -> click.Command:
    from datetime import datetime

    from ..ledger import FinanceRef, TraceEntry, load_ledger, save_ledger

    @click.command("record", help="Append a SKU/offer/listing/trace/finance entry to a ledger.")
    @click.option("--run-id", required=True, help="Run id to record against.")
    @click.option("--sku", multiple=True, help="Test SKU created (repeatable).")
    @click.option("--offer-id", multiple=True, help="Offer id created (repeatable).")
    @click.option("--listing-id", multiple=True, help="Published listing id (repeatable).")
    @click.option("--request-id", default=None, help="x-ebay-c-request-id for the trace entry.")
    @click.option("--trace-id", default=None, help="x-traffic-request-id for the trace entry.")
    @click.option("--operation", default=None, help="Operation key this trace entry refers to.")
    @click.option("--finance", multiple=True,
                  help="Observed finance charge as TYPE=AMT:CUR[:listing-id] (repeatable).")
    @click.pass_context
    def _cmd(ctx, run_id, sku, offer_id, listing_id, request_id, trace_id,
             operation, finance):
        context: CliContext = ctx.obj
        base = _ledger_base_dir(context)
        ledger = load_ledger(run_id, base_dir=base)
        for s in sku:
            ledger.add_test_sku(s)
        for o in offer_id:
            ledger.add_offer(o)
        for li in listing_id:
            ledger.add_listing(li)
        if request_id or trace_id or operation:
            ledger.add_trace(TraceEntry(
                operation=operation or "",
                timestamp=datetime.now(UTC).isoformat(),
                request_id=request_id, trace_id=trace_id,
            ))
        for spec in finance:
            parsed = _parse_finance(spec)
            if parsed:
                parsed["timestamp"] = datetime.now(UTC).isoformat()
                ledger.add_finance(FinanceRef(**parsed))
        path = save_ledger(ledger, base_dir=base)
        emit_json({"run_id": run_id, "ledger_file": str(path),
                   "test_skus": ledger.test_skus, "offer_ids": ledger.offer_ids,
                   "listing_ids": ledger.listing_ids,
                   "finance_charges": len(ledger.finance_refs)}, pretty=context.pretty)

    return _cmd


def _parse_finance(spec: str) -> dict:
    """Parse a --finance TYPE=AMT:CUR[:listing-id] token."""
    if "=" not in spec:
        return {}
    ftype, _, rest = spec.partition("=")
    parts = rest.split(":")
    amount = parts[0] if parts else None
    currency = parts[1] if len(parts) > 1 else None
    listing_id = parts[2] if len(parts) > 2 else None
    return {"transaction_type": ftype or None, "amount": amount,
            "currency": currency, "listing_id": listing_id}


def _test_run_show_command() -> click.Command:
    from ..ledger import load_ledger

    @click.command("show", help="Print a ledger as JSON.")
    @click.option("--run-id", required=True)
    @click.pass_context
    def _cmd(ctx, run_id):
        context: CliContext = ctx.obj
        base = _ledger_base_dir(context)
        ledger = load_ledger(run_id, base_dir=base)
        emit_json(ledger.to_dict(), pretty=context.pretty)

    return _cmd


def _test_run_cleanup_report_command() -> click.Command:
    from ..dispatch import resolve_resource
    from ..ledger import cleanup_report, load_ledger

    @click.command("cleanup-report",
                   help="Check current seller + public state for a run's records and report.")
    @click.option("--run-id", required=True)
    @public_poll_options()
    @click.pass_context
    def _cmd(ctx, run_id, wait_seconds, poll_interval):
        context: CliContext = ctx.obj
        if context.dry_run:
            emit_json({"dry_run": True, "workflow": "sell_inventory.test_run.cleanup_report",
                       "run_id": run_id}, pretty=context.pretty)
            return
        base = _ledger_base_dir(context)
        ledger = load_ledger(run_id, base_dir=base)
        manifest = context.manifest
        seller_state: dict[str, str] = {}
        frontend_state: dict[str, str] = {}

        # Seller-side reads for each recorded SKU (getInventoryItem).
        inv_op = manifest.get("sell_inventory.getInventoryItem")
        if inv_op is not None and ledger.test_skus:
            resource = resolve_resource(context.client, manifest.service(inv_op.service_key))
            method = getattr(resource, inv_op.python_method)
            for sku in ledger.test_skus:
                seller_state[sku] = _read_seller_state(lambda s=sku: method(s, raw_response=True))

        # Seller-side reads for each recorded offer (getOffer).
        offer_op = manifest.get("sell_inventory.getOffer")
        if offer_op is not None and ledger.offer_ids:
            resource = resolve_resource(context.client, manifest.service(offer_op.service_key))
            method = getattr(resource, offer_op.python_method)
            for offer_id in ledger.offer_ids:
                seller_state[offer_id] = _read_seller_state(
                    lambda o=offer_id: method(o, raw_response=True))

        # When every recorded seller record is gone, any still-public listing from
        # this run is stale (not active): the run has no live inventory to back
        # it. This lets the report name stale_after_delete even though the
        # listing->SKU mapping is not stored on the ledger.
        seller_ids = [*ledger.test_skus, *ledger.offer_ids]
        all_seller_deleted = bool(seller_ids) and all(
            seller_state.get(sid) == "deleted" for sid in seller_ids
        )

        # Public/Browse reads for each recorded listing id. Pass the recorded
        # SKU so verify_public reads the seller side and the combined state can
        # reach ``not_listed`` (seller deleted + public ended) instead of being
        # stuck at ``public_ended`` / ``stale_after_delete``.
        if ledger.listing_ids:
            from ..workflows import verify_public

            public_listing_state: dict[str, str] = {}
            for listing_id in ledger.listing_ids:
                sku = _sku_for_listing(ledger, listing_id)
                report = verify_public(
                    context, listing_id=listing_id, sku=sku,
                    expect_browse="not_found",
                    wait_seconds=wait_seconds, poll_interval=poll_interval,
                )
                state = report["frontend_state"]
                if (
                    state == "visible"
                    and all_seller_deleted
                    and report.get("api_state") == "not_checked"
                ):
                    state = "stale_after_delete"
                frontend_state[listing_id] = state
                public_listing_state[listing_id] = report.get("public_listing_state", "not_checked")

        # Finance is an observation, not a guarantee. We do not auto-read
        # finances here (that needs account-scoped params); the status stays
        # whatever the ledger recorded, defaulting to not_checked.
        emit_json(cleanup_report(ledger, seller_state=seller_state,
                                 frontend_state=frontend_state,
                                 public_listing_state=public_listing_state),
                  pretty=context.pretty)

    return _cmd


_EXECUTE_HELP = (
    "Plan, gate, and (optionally) idempotently clean up a controlled test run. "
    "The create/publish steps use the normal inventory/offer commands with "
    "--test-run-id, which auto-record every SKU/offer/listing id to the "
    "durable ledger, so this command focuses on the dangerous, "
    "correlation-sensitive part: it prints a plan, requires the destructive "
    "mutation gate (--allow-write --yes), then withdraws and deletes every "
    "recorded offer and inventory item and produces a per-record cleanup "
    "report. Re-runnable: a 404 on withdraw/delete counts as already-clean."
)


def _test_run_execute_command() -> click.Command:
    from datetime import datetime

    from ..ledger import RunLedger, load_ledger, new_run_id, save_ledger

    @click.command("execute", help=_EXECUTE_HELP)
    @click.option("--run-id", default=None, help="Run id (created if absent).")
    @click.option("--source-sku", "source_skus", multiple=True,
                  help="Real source SKU cross-wired into the test (repeatable).")
    @click.option("--test-sku", "test_skus", multiple=True,
                  help="Test SKU to record against this run for planning and "
                       "cleanup tracking (repeatable). The inventory item itself "
                       "is created with the normal commands and --test-run-id.")
    @click.option("--cleanup", is_flag=True, default=False,
                  help="Withdraw + delete every recorded offer/inventory item, then report.")
    @click.option("--plan-only", is_flag=True, default=False,
                  help="Print the plan and exit without cleaning up.")
    @public_poll_options()
    @click.pass_context
    def _cmd(ctx, run_id, source_skus, test_skus,
             cleanup, plan_only, wait_seconds, poll_interval):
        context: CliContext = ctx.obj
        base = _ledger_base_dir(context)
        rid = run_id or new_run_id()
        # Load the existing (auto-recorded) ledger if present, or init a fresh
        # one in memory. Reading is allowed in every mode so the plan reflects
        # what is really recorded; the persistence decision is made below so the
        # preview modes (--plan-only, global --dry-run) never touch the
        # filesystem.
        try:
            ledger = load_ledger(rid, base_dir=base)
        except FileNotFoundError:
            ledger = RunLedger(run_id=rid, created_at=datetime.now(UTC).isoformat())
        # Seed SKUs are merged in memory either way — silently dropping
        # --source-sku/--test-sku on an existing ledger would make the flags
        # no-ops after the first auto-recorded write. No I/O happens here.
        for sku in source_skus:
            if sku not in ledger.source_skus:
                ledger.source_skus.append(sku)
        for sku in test_skus:
            ledger.add_test_sku(sku)

        plan = {
            "workflow": "sell_inventory.test_run.execute",
            "run_id": rid,
            "source_skus": ledger.source_skus,
            "test_skus": ledger.test_skus,
            "recorded_offers": ledger.offer_ids,
            "recorded_listings": ledger.listing_ids,
            "will_cleanup": cleanup,
            "note": (
                "Create/publish with the normal commands and --test-run-id; "
                "they auto-record to this ledger. This command plans, gates, "
                "and cleans up."
            ),
        }
        # Preview modes render an accurate plan but must NOT create, save, or
        # update the ledger: an agent surveying a run with --plan-only or
        # --dry-run expects no side effects. The ledger may be read above, but
        # nothing is written before returning.
        if plan_only or context.dry_run:
            emit_json(plan, pretty=context.pretty)
            return
        if not cleanup:
            # Normal non-preview path: persist the merged seeds, then report.
            save_ledger(ledger, base_dir=base)
            emit_json(plan, pretty=context.pretty)
            return
        # Cleanup withdraws AND deletes, which are destructive mutations. The
        # documented contract (SKILL.md, safety reference, and the generated
        # delete-* commands) is --allow-write --yes; the command's own hint said
        # so but the code never checked --yes. Both gates are now enforced, and
        # the hint matches exactly. The gate is checked before any write so a
        # refusal leaves the ledger untouched.
        if not context.allow_write or not context.yes:
            raise SafetyError(
                "test-run execute --cleanup withdraws and deletes seller records; "
                "this is destructive and requires both --allow-write and --yes.",
                hint="bidkit sell inventory test-run execute --run-id RID "
                     "--cleanup --allow-write --yes",
            )
        # Persist the merged seeds before the destructive cleanup so the run's
        # intent is durable even if cleanup crashes partway.
        save_ledger(ledger, base_dir=base)
        # Idempotent cleanup: withdraw + delete each offer, delete each SKU.
        report = _cleanup_run(context, ledger, base,
                              wait_seconds=wait_seconds, poll_interval=poll_interval)
        emit_json(report, pretty=context.pretty)

    return _cmd


def _cleanup_run(
    context: CliContext, ledger, base, *, wait_seconds: float,
    poll_interval: float,
) -> dict:
    """Withdraw+delete recorded offers/SKUs, then produce the cleanup report.

    Idempotent: a 404 on withdraw/delete means already-clean and is treated as
    success. Re-runnable after a partial failure. Each mutation is recorded to
    the ledger's event stream (the recorder is bypassed because we call SDK
    resources directly here), cleanup_status is advanced to
    ``complete`` on success, and the public-state readback is given the recorded
    SKU so the report can name ``not_listed`` (seller deleted AND public ended)
    instead of leaving the seller side ``not_checked``.
    """
    from ..dispatch import resolve_resource
    from ..ledger import CLEANUP_COMPLETE, CLEANUP_IN_PROGRESS, cleanup_report, save_ledger

    manifest = context.manifest
    withdraw_op = manifest.get("sell_inventory.withdrawOffer")
    delete_offer_op = manifest.get("sell_inventory.deleteOffer")
    delete_item_op = manifest.get("sell_inventory.deleteInventoryItem")
    offer_state: dict[str, str] = {}
    sku_state: dict[str, str] = {}

    # Mark the run in-progress so a crash mid-cleanup is visible on the ledger.
    ledger.cleanup_status = CLEANUP_IN_PROGRESS
    save_ledger(ledger, base_dir=base)

    def _do(op, resource, arg, target, *, sku=None):
        if op is None or resource is None:
            return
        method = getattr(resource, op.python_method, None)
        if method is None:
            return
        try:
            resp = method(arg, raw_response=True)
        except Exception:  # noqa: BLE001
            target[arg] = "not_checked"
            return
        status = resp.status_code if isinstance(resp, httpx2.Response) else None
        # 200/204 = deleted; 404 = already gone (idempotent success).
        if isinstance(resp, httpx2.Response):
            target[arg] = "deleted" if resp.status_code in {200, 204, 404} else "present"
        else:
            target[arg] = "deleted"
        # Record the cleanup mutation so the event stream reflects the whole
        # lifecycle, not just the create/publish half. We append to the
        # in-memory ledger (the run's final save persists it) so the events are
        # not clobbered by a separate load/save cycle.
        with contextlib.suppress(Exception):
            from ..dispatch import _append_cleanup_event

            _append_cleanup_event(
                ledger, op, status, arg, sku=sku,
                request_id=(resp.headers.get("x-ebay-c-request-id")
                            if isinstance(resp, httpx2.Response) else None),
            )

    if withdraw_op is not None:
        res = resolve_resource(context.client, manifest.service(withdraw_op.service_key))
        for offer_id in ledger.offer_ids:
            _do(withdraw_op, res, offer_id, offer_state)
    if delete_offer_op is not None:
        res = resolve_resource(context.client, manifest.service(delete_offer_op.service_key))
        for offer_id in ledger.offer_ids:
            _do(delete_offer_op, res, offer_id, offer_state)
    if delete_item_op is not None:
        res = resolve_resource(context.client, manifest.service(delete_item_op.service_key))
        for sku in ledger.test_skus:
            _do(delete_item_op, res, sku, sku_state, sku=sku)

    # A fully successful cleanup advances cleanup_status. A run with no seller
    # records at all (e.g. only listing ids were recorded) is vacuously complete
    # — there is nothing seller-side left to delete — rather than being parked
    # at ``in_progress`` forever.
    seller_ids = [*ledger.test_skus, *ledger.offer_ids]
    all_deleted = all(
        {**sku_state, **offer_state}.get(sid) == "deleted" for sid in seller_ids
    )
    if all_deleted:
        ledger.cleanup_status = CLEANUP_COMPLETE
    save_ledger(ledger, base_dir=base)

    # Final per-record readback. Pass the recorded SKU for each listing so
    # verify_public reads the seller side and the combined state can reach
    # ``not_listed`` (seller deleted + public ended) instead of being stuck at
    # ``public_ended``.
    seller_state = {**sku_state, **offer_state}
    frontend_state: dict[str, str] = {}
    public_listing_state: dict[str, str] = {}
    if ledger.listing_ids:
        from ..workflows import verify_public

        for listing_id in ledger.listing_ids:
            sku = _sku_for_listing(ledger, listing_id)
            rep = verify_public(context, listing_id=listing_id, sku=sku,
                                expect_browse="not_found",
                                wait_seconds=wait_seconds,
                                poll_interval=poll_interval)
            frontend_state[listing_id] = rep["frontend_state"]
            public_listing_state[listing_id] = rep.get("public_listing_state", "not_checked")
    return cleanup_report(ledger, seller_state=seller_state,
                          frontend_state=frontend_state,
                          public_listing_state=public_listing_state)


def _sku_for_listing(ledger, listing_id: str) -> str | None:
    """Best-effort SKU for a listing id, from the event stream.

    The publishOffer event recorded the offer id alongside the listing id; the
    createOffer event recorded the SKU alongside the offer id. We walk the
    event stream to recover the SKU for a listing so the cleanup readback can
    read the seller-side inventory state.
    """
    offer_for_listing = None
    for event in ledger.events:
        if event.operation == "sell_inventory.publishOffer" and event.listing_id == listing_id:
            offer_for_listing = event.offer_id
            break
    if offer_for_listing is None:
        return None
    for event in ledger.events:
        if event.operation == "sell_inventory.createOffer" and event.offer_id == offer_for_listing:
            return event.sku
    return None


def _read_seller_state(call) -> str:
    """Classify a getInventoryItem/getOffer response as present/deleted."""
    import httpx2

    try:
        response = call()
    except Exception:
        return "not_checked"
    if isinstance(response, httpx2.Response):
        if response.status_code == 200:
            return "present"
        if response.status_code == 404:
            return "deleted"
        return "not_checked"
    return "present" if response is not None else "deleted"


# ---------------------------------------------------------------------------
# buy purchases capability
# ---------------------------------------------------------------------------

_PURCHASES_CAPABILITY_HELP = (
    "Report whether member (buyer) purchase history is reachable from the "
    "current CLI/OAS surface. The generated buy_order service covers GUEST "
    "checkout only; there is no member purchase-order operation and the "
    "configured OAuth scopes contain no buyer-order scope. Never infer 'no "
    "purchases' from a logged-out page or mistake seller orders for purchases."
)


def _inject_buy_purchases(namespace_groups: list[click.Group]) -> None:
    buy = _find_group(namespace_groups, "buy")
    if buy is None:
        return
    # Do not shadow a generated ``purchases`` service if one ever appears.
    if "purchases" in buy.commands:
        return
    purchases = click.Group(
        "purchases",
        help=(
            "Member (buyer) purchase history. The current OAS surface exposes "
            "guest checkout only; use `bidkit buy purchases capability` to see "
            "whether member purchases are reachable before trying to list them."
        ),
    )
    purchases.add_command(_purchases_capability_command())
    buy.add_command(purchases)


def _purchases_capability_command() -> click.Command:
    from ..capabilities import member_purchase_capability

    @click.command(
        "capability",
        help=_PURCHASES_CAPABILITY_HELP,
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    @click.option("--browser-cdp", default=None,
                  help="Chrome DevTools Protocol endpoint for an optional authenticated fallback.")
    @click.pass_context
    def _cmd(ctx: click.Context, browser_cdp: str | None) -> None:
        context: CliContext = ctx.obj
        if context.dry_run:
            emit_json(
                {
                    "dry_run": True,
                    "workflow": "buy.purchases.capability",
                    "note": "Reports capability only; performs no network call.",
                },
                pretty=context.pretty,
            )
            return
        emit_json(member_purchase_capability(browser_cdp=browser_cdp), pretty=context.pretty)

    return _cmd


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _find_group(commands: Any, name: str) -> click.Group | None:
    """Find a subgroup or command by name within a Click group/iterable."""
    iterable = commands.values() if hasattr(commands, "values") else commands
    for command in iterable:
        if getattr(command, "name", None) == name and isinstance(command, click.Group):
            return command
    return None


__all__ = [
    "FRONTEND_STATES",
    "inject_workflow_commands",
]
