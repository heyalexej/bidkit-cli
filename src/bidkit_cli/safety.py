"""Mutation safety model (spec §14).

Every operation carries a generated ``risk`` (read/write/destructive/unknown)
derived from its HTTP method. POST is ``unknown`` by default and the CLI fails
*closed* until a curated override classifies it.

The override table is hand-curated source here, *not* generated data: it is a
compatibility-sensitive decision that belongs in review, not in the manifest.
Every entry must reference a real manifest operation (see
:func:`validate_overrides`, exercised by the test suite), so a stale id fails
loudly instead of lending false confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .errors import SafetyError
from .manifest import Manifest, OperationRecord, Risk

Classification = Literal["read_only", "external_side_effect", "write", "destructive"]


@dataclass(frozen=True)
class RiskOverride:
    """A reviewed safety decision for one operation.

    ``read_only`` downgrades a POST to ``read`` (it retrieves data).

    ``write`` classifies a POST as a write (it mutates seller/account state);
    such an op needs ``--allow-write`` but NOT ``--yes``.

    ``destructive`` classifies a POST as destructive; it needs ``--allow-write``
    AND ``--yes`` (same gate as a DELETE).

    ``external_side_effect`` keeps the operation blocked (it is not a data
    mutation but has an observable external effect, e.g. triggering a
    notification delivery) and surfaces a specific reason instead of the generic
    "unclassified" hint.
    """

    operation_key: str
    classification: Classification
    reason: str


# Reviewed POST classifications. Add an entry only after confirming the call's
# behavior; keep the reason specific so a reviewer can audit it. GET/HEAD/OPTIONS
# never need an entry — they are already ``read``.
#
# Evidence notes:
# - searchByImage / translate: eBay uses POST for these because the request body
#   is too large for a query string; both only return data.
# - findListingRecommendations: the Find Listing Recommendations API returns
#   suggestions and writes nothing (verified read-only during live review).
# - testSubscription: deliberately *not* read-only — it forces eBay to deliver a
#   real notification to an external endpoint, so it stays blocked.
# The canonical sell workflow (createOffer / publishOffer / withdrawOffer) and
# the media image upload (createImageFromFile) are POSTs with no generated risk
# classification, so the safety gate refused them until the "expert unclassified"
# escape hatch was supplied — the flag whose own hint describes forcing an
# *unclassified* call. They are the center of the product's own publish recipe,
# so they are curated here as reviewed writes: the normal --allow-write gate (no
# --yes, no expert flag) now carries them.
_OVERRIDES: tuple[RiskOverride, ...] = (
    RiskOverride(
        "buy_browse.searchByImage",
        "read_only",
        "Image search; the POST body only carries the image, no state changes.",
    ),
    RiskOverride(
        "commerce_translation.translate",
        "read_only",
        "Returns a translation; no account state mutation.",
    ),
    RiskOverride(
        "sell_recommendation.findListingRecommendations",
        "read_only",
        "Find Listing Recommendations API returns suggestions; writes nothing.",
    ),
    RiskOverride(
        "commerce_notification.testSubscription",
        "external_side_effect",
        "Triggers a real notification delivery to an external endpoint; not a "
        "data mutation but not safe to call as a read.",
    ),
    # Canonical sell lifecycle: create an offer, publish it, withdraw it. Each
    # mutates seller state but is reversible/non-destructive (no DELETE), so the
    # write gate is the right level — not the destructive two-gate, and not the
    # unclassified expert escape hatch.
    RiskOverride(
        "sell_inventory.createOffer",
        "write",
        "Creates an offer record; a normal write (reversible via deleteOffer).",
    ),
    RiskOverride(
        "sell_inventory.publishOffer",
        "write",
        "Publishes an offer to a live listing; a normal write (reversible via "
        "withdrawOffer).",
    ),
    RiskOverride(
        "sell_inventory.withdrawOffer",
        "write",
        "Withdraws a published offer; a normal write (the listing becomes "
        "unpurchasable but is not deleted).",
    ),
    RiskOverride(
        "commerce_media.createImageFromFile",
        "write",
        "Uploads a media image; a normal write (reversible via the media delete).",
    ),
)

_OVERRIDE_MAP: dict[str, RiskOverride] = {o.operation_key: o for o in _OVERRIDES}


def override_for(operation: OperationRecord) -> RiskOverride | None:
    return _OVERRIDE_MAP.get(operation.key)


def effective_risk(operation: OperationRecord) -> tuple[Risk, str | None]:
    """Apply curated overrides on top of the generated base risk."""
    override = override_for(operation)
    if override is None:
        return operation.risk, None
    if override.classification == "read_only":
        return "read", override.reason
    if override.classification == "write":
        return "write", override.reason
    if override.classification == "destructive":
        return "destructive", override.reason
    # external_side_effect: stays blocked (unknown) but with a documented reason.
    return "unknown", override.reason


def classify_safety(
    operation: OperationRecord,
    *,
    allow_write: bool,
    allow_write_expert: bool,
    yes: bool,
) -> tuple[Risk, str | None]:
    """Return the effective risk, raising if the invocation policy refuses it.

    The policy is explicit and truthful about every flag:

    * ``read`` runs normally.
    * ``write`` (PUT/PATCH) requires ``allow_write``.
    * ``destructive`` (DELETE) requires ``allow_write`` and ``yes``.
    * ``unknown`` (an unclassified POST) requires ``allow_write_expert`` *and*
      ``yes`` — the CLI cannot know whether an unclassified POST mutates account
      state, so forcing it is a deliberate two-gate expert action.
    * an ``external_side_effect`` override (``unknown`` with a reason) is *not*
      overridable by ``--allow-write-expert``: it triggers an observable external
      effect (e.g. a real notification delivery), not a data mutation.

    ``--dry-run`` is always allowed and is handled by the caller; this only
    governs whether a *real* request may leave the process.
    """
    risk, reason = effective_risk(operation)
    if risk == "read":
        return risk, reason
    if risk == "unknown":
        # A documented reason on an unknown risk is an external-side-effect
        # override: it stays blocked even in expert mode, and the hint must not
        # claim that --allow-write-expert will force it.
        if reason:
            raise SafetyError(
                f"{operation.key} is blocked: {reason}",
                operation=operation.key,
                risk=risk,
                hint=(
                    "This operation triggers an external side effect and is not "
                    "overridable with --allow-write-expert."
                ),
            )
        # Unclassified POST: expert mode is the only way through, and it needs
        # both --allow-write-expert and an explicit --yes confirmation.
        if not allow_write_expert:
            raise SafetyError(
                f"{operation.key} is a {operation.http_method} request with no read "
                "classification; refusing to run until it is classified or explicitly forced.",
                operation=operation.key,
                risk=risk,
                hint=(
                    "Re-run with --allow-write-expert to force this unclassified call, "
                    "or add it to the override table in bidkit_cli/safety.py if it is read-only."
                ),
            )
        if not yes:
            raise SafetyError(
                f"{operation.key} is an unclassified {operation.http_method} request; "
                "expert mode requires explicit confirmation.",
                operation=operation.key,
                risk=risk,
                hint="Re-run with --allow-write-expert --yes to confirm.",
            )
        return risk, reason
    if risk in {"write", "destructive"} and not allow_write:
        raise SafetyError(
            f"{operation.key} is classified {risk.upper()} and mutates account state.",
            operation=operation.key,
            risk=risk,
            hint="Re-run with --allow-write to permit this mutation.",
        )
    if risk == "destructive" and not yes:
        raise SafetyError(
            f"{operation.key} is DESTRUCTIVE and can delete seller/account state.",
            operation=operation.key,
            risk=risk,
            hint="Re-run with --allow-write --yes to confirm the destructive operation.",
        )
    return risk, reason


def validate_overrides(manifest: Manifest) -> list[str]:
    """Fail loudly if any override key is absent from the manifest or is a no-op.

    Returns a list of human-readable warnings (empty when clean). A missing key
    means the override is dead (the operation was renamed/removed upstream); a
    no-op means the base risk already matches (e.g. a GET marked read), which
    adds nothing and should be removed to keep the table meaningful.
    """
    problems: list[str] = []
    for override in _OVERRIDES:
        operation = manifest.get(override.operation_key)
        if operation is None:
            problems.append(
                f"override {override.operation_key!r} is not in the manifest "
                "(stale operation id)"
            )
            continue
        if operation.risk == "read" and override.classification == "read_only":
            problems.append(
                f"override {override.operation_key!r} is redundant: base risk is "
                "already read"
            )
        if operation.http_method != "POST":
            problems.append(
                f"override {override.operation_key!r} targets a {operation.http_method} "
                "request; only POSTs need classification"
            )
    return problems
