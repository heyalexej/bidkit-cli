"""``bidkit capabilities`` — capability discovery.

Generated OAS coverage says an operation *exists*; it does not say an account
can call it. This command surfaces the hand-maintained capability policy
(:mod:`bidkit_cli.capability_policy`) merged with the generated manifest, so an
agent can see which surfaces are available, which are restricted (Leads, eDIS,
VeRO, Buy bulk/Deal/Marketing), which are stale (Compliance PBSE), and which are
upstream-broken (awaiting feedback) — without inferring availability from a
single failing call.

Default output is bounded and never exposes access tokens, raw response bodies,
lead contact information, or seller addresses.
"""

from __future__ import annotations

from typing import Any

import click

from ..capability_policy import (
    AVAILABILITY_AVAILABLE,
    capability_for,
)
from ..context import CliContext
from ..errors import UsageError
from ..manifest import Manifest, OperationRecord
from ..rendering import emit_json


def _policy_view(op: OperationRecord) -> dict[str, Any]:
    """The capability record for one operation (policy + OAS facts)."""
    policy = capability_for(op.key)
    view: dict[str, Any] = {
        "operation": op.key,
        "service": op.service_key,
        "namespace": op.namespace,
        "cli_command": " ".join(op.cli_path),
        "risk": op.risk,
        "oas": True,
        "availability": policy.availability if policy else AVAILABILITY_AVAILABLE,
        # required_scopes are the OAS-declared (authoritative) scopes; the
        # policy's required_scopes are documentation labels for the same grants
        # and are not merged here to avoid duplicate forms of one scope.
        "required_scopes": list(op.auth.scopes),
        "account_requirement": policy.account_requirement if policy else None,
        "production_approval": policy.production_approval if policy else None,
        "membership": policy.membership if policy else None,
        "fallback": policy.fallback if policy else None,
        "retry_on_failure": policy.retry if policy else True,
        "references": policy.references if policy else [],
        "note": policy.note if policy else None,
    }
    return view


def _scope_grant_status(view: dict[str, Any], configured_scopes: set[str]) -> dict[str, Any]:
    """Whether the configured scopes satisfy the operation's required scopes."""
    required = view.get("required_scopes") or []
    if not required:
        return {"required_scopes_granted": True, "missing_scopes": []}
    missing = sorted({s for s in required if s not in configured_scopes})
    return {"required_scopes_granted": not missing, "missing_scopes": missing}


@click.group("capabilities", help="Show which generated operations this account can actually use.")
def capabilities_group() -> None:
    pass


@capabilities_group.command("list")
@click.option("--status", default=None,
              help="Filter by availability label (e.g. unavailable, limited_release, "
                   "account_restricted, stale_or_not_applicable).")
@click.option("--service", default=None, help="Filter by service key.")
@click.option("--all", "show_all", is_flag=True, default=False,
              help="Include every operation, not just the curated restricted/broken "
                   "surfaces (default: only operations the capability policy curates).")
@click.option("--scope-blocked", "scope_blocked", is_flag=True, default=False,
              help="Only operations this account's scopes do NOT cover.")
@click.option("--granted", "granted_only", is_flag=True, default=False,
              help="Only operations this account's scopes DO cover.")
@click.pass_context
def capabilities_list(
    ctx: click.Context,
    status: str | None,
    service: str | None,
    show_all: bool,
    scope_blocked: bool,
    granted_only: bool,
) -> None:
    """List capability availability across the generated surface.

    The default listing is sized for an agent — only the operations the
    capability policy actually curates (restricted/broken/stale surfaces) plus a
    summary, instead of all ~455 operations × ~20 mostly-null fields. Pass
    ``--all`` for the full dump.

    ``--scope-blocked`` / ``--granted`` answer "what can this account actually
    call right now" by comparing each operation's required scopes against the
    configured grant. They scan the whole surface rather than the curated view:
    a missing scope is a property of the grant, not of eBay's capability policy,
    so restricting the scan to curated entries would hide most of the answer.
    """
    context: CliContext = ctx.obj
    manifest = context.manifest
    configured_scopes = _configured_scopes(context)
    if scope_blocked and granted_only:
        raise UsageError("--scope-blocked and --granted are opposites; pass one")
    scope_filter = scope_blocked or granted_only
    if scope_filter and configured_scopes is None:
        raise UsageError(
            "no configured scopes to compare against",
            hint="run `bidkit auth doctor` to check the config, then `bidkit auth login`",
        )
    views = []
    for op in manifest.operations:
        if service and op.service_key != service:
            continue
        policy = capability_for(op.key)
        # Default view = restricted/degraded surfaces only. A policy that merely
        # annotates availability (``available``) is not a restriction, so it is
        # excluded from the default listing and only appears with --all. A scope
        # filter overrides that: it asks about the grant, not the policy.
        if (
            not show_all
            and not scope_filter
            and (policy is None or policy.availability == AVAILABILITY_AVAILABLE)
        ):
            continue
        view = _policy_view(op)
        if configured_scopes is not None:
            view.update(_scope_grant_status(view, configured_scopes))
        if scope_blocked and view.get("required_scopes_granted", True):
            continue
        if granted_only and not view.get("required_scopes_granted", True):
            continue
        if status == "unavailable" and view["availability"] == AVAILABILITY_AVAILABLE:
            continue
        if status and status != "unavailable" and view["availability"] != status:
            continue
        views.append(view)
    summary: dict[str, int] = {}
    for view in views:
        summary[view["availability"]] = summary.get(view["availability"], 0) + 1
    payload: dict[str, Any] = {
        "summary": dict(sorted(summary.items())),
        "operation_count": len(views),
        "default_view": "curated" if not show_all else "all",
        "capabilities": views,
    }
    if configured_scopes is not None:
        payload["account"] = {"configured_scopes": sorted(configured_scopes)}
    emit_json(payload, pretty=context.pretty)


@capabilities_group.command("describe")
@click.argument("operation", required=True)
@click.pass_context
def capabilities_describe(ctx: click.Context, operation: str) -> None:
    """Show the full capability record for one operation (OAS + policy).

    A near-miss operation key is fuzzy-resolved via the manifest's alias
    resolver and suggests candidates, instead of a bare "no operation matches".
    """
    context: CliContext = ctx.obj
    manifest = context.manifest
    try:
        op = manifest.resolve(operation)
    except Exception as exc:  # noqa: BLE001
        suggestions = _suggest_operations(manifest, operation)
        hint = None
        if suggestions:
            hint = "did you mean: " + ", ".join(suggestions[:5])
        raise UsageError(str(exc), hint=hint) from exc
    view = _policy_view(op)
    configured_scopes = _configured_scopes(context)
    if configured_scopes is not None:
        view.update(_scope_grant_status(view, configured_scopes))
        view["account"] = {"configured_scopes": sorted(configured_scopes)}
    emit_json(view, pretty=context.pretty)


def _suggest_operations(manifest: Manifest, query: str) -> list[str]:
    """Best-effort candidate operation keys for a near-miss query.

    Combines a substring sweep with a fuzzy edit-distance match (difflib) over
    the operation id and cli name (the segments an agent actually types), so a
    typo like ``getItm`` still suggests ``buy_browse.getItem``.
    """
    import difflib

    q = query.lower().replace("-", "_")
    candidates: list[str] = []
    for op in manifest.operations:
        if q in op.key.lower() or q in op.cli_name.lower().replace("-", "_"):
            candidates.append(op.key)
    if candidates:
        return candidates
    # Fuzzy edit-distance over the short segments an agent types (operation id,
    # cli name), mapped back to the canonical key.
    by_segment: dict[str, str] = {}
    for op in manifest.operations:
        by_segment.setdefault(op.operation_id.lower(), op.key)
        by_segment.setdefault(op.cli_name.lower().replace("-", "_"), op.key)
    close = difflib.get_close_matches(q, list(by_segment), n=5, cutoff=0.6)
    seen: list[str] = []
    for seg in close:
        key = by_segment[seg]
        if key not in seen:
            seen.append(key)
    return seen


def _configured_scopes(context: CliContext) -> set[str] | None:
    """Best-effort read of configured scopes (offline; never raises)."""
    try:
        return set(context.config.scopes)
    except Exception:  # noqa: BLE001 - capabilities must work without a config file
        return None


def capabilities_snapshot(context: CliContext) -> dict[str, Any]:
    """A compact capability snapshot for ``auth doctor --show-capabilities``."""
    manifest = context.manifest
    configured = _configured_scopes(context)
    rows = []
    for op in manifest.operations:
        policy = capability_for(op.key)
        if policy is None:
            continue  # only restricted/broken surfaces appear in the doctor view
        view = _policy_view(op)
        if configured is not None:
            view.update(_scope_grant_status(view, configured))
        rows.append(view)
    return {
        "restricted_or_broken_operations": len(rows),
        "capabilities": rows,
        "note": (
            "Generated operations remain directly callable; these labels say "
            "whether the account is *expected* to succeed, not whether the OAS "
            "operation exists."
        ),
    }


__all__ = ["capabilities_group"]
