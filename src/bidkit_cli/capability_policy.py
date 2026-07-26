"""Capability policy: which operations are *expected* to work for this account.

Generated OAS coverage says an operation *exists*; it does not say an account
can call it. eBay restricts several surfaces behind scopes the account does not
hold, memberships, partner/production approvals, or account eligibility, and one
surface (Compliance PBSE) has been rolled back. The remedy is a
generated-but-overridable capability manifest that distinguishes static facts
(OAS existence, documented scopes) from account-specific restrictions a small
hand-maintained policy file expresses.

This module is that policy file. It is deliberately small and explicit: each
entry names the restriction, the remedy, and whether to retry a failure. The
``bidkit capabilities`` command and ``auth doctor --show-capabilities`` read it,
and the error classifier consults :func:`hint_for_failure` so a 403/500 on a
restricted surface produces an actionable hint instead of a raw status.

Official references are cited inline so a future change can be traced to the
source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Availability labels surfaced in capability output.
AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_LIMITED_RELEASE = "limited_release"
AVAILABILITY_PRODUCTION_ENTITLEMENT = "production_entitlement_required"
AVAILABILITY_MEMBERSHIP_RESTRICTED = "membership_restricted"
AVAILABILITY_ACCOUNT_RESTRICTED = "account_restricted"
AVAILABILITY_UPSTREAM_FAILURE = "upstream_failure"
AVAILABILITY_STALE = "stale_or_not_applicable"


@dataclass
class CapabilityPolicy:
    """One operation's expected availability and restriction metadata."""

    availability: str
    required_scopes: list[str] = field(default_factory=list)
    account_requirement: str | None = None
    production_approval: str | None = None
    membership: str | None = None
    fallback: str | None = None
    note: str | None = None
    retry: bool = True
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"availability": self.availability}
        if self.required_scopes:
            payload["required_scopes"] = self.required_scopes
        if self.account_requirement:
            payload["account_requirement"] = self.account_requirement
        if self.production_approval:
            payload["production_approval"] = self.production_approval
        if self.membership:
            payload["membership"] = self.membership
        if self.fallback:
            payload["fallback"] = self.fallback
        if self.note:
            payload["note"] = self.note
        payload["retry_on_failure"] = self.retry
        if self.references:
            payload["references"] = self.references
        return payload


# ---------------------------------------------------------------------------
# Hand-maintained policy. Keys are canonical operation keys or service keys
# (``sell_leads.*`` applies to every operation in the sell_leads service).
# ---------------------------------------------------------------------------

_POLICY: dict[str, CapabilityPolicy] = {
    # awaiting feedback: the account HAS commerce.feedback and the sibling
    # reads work; the endpoint currently returns HTTP 500. This is an upstream/
    # account-state failure, NOT a scope problem, so retry is bounded and the
    # scope is not flagged as the remedy. A Trading API fallback is a distinct
    # endpoint/credential flow and is named explicitly, never substituted.
    "commerce_feedback.getItemsAwaitingFeedback": CapabilityPolicy(
        availability=AVAILABILITY_UPSTREAM_FAILURE,
        required_scopes=["commerce.feedback"],
        note=(
            "Currently returns HTTP 500 upstream even though the account holds "
            "commerce.feedback and getFeedback/getFeedbackRatingSummary succeed. "
            "Retry later; this is not a scope problem."
        ),
        retry=True,
        fallback="trading.GetItemsAwaitingFeedback",
        references=[
            "https://developer.ebay.com/develop/api/buy/feedback_api",
            "https://developer.ebay.com/DevZone/XML/docs/Reference/eBay/GetItemsAwaitingFeedback.html",
        ],
    ),
    # Leads: Limited Release, requires sell.leads AND eBay business-unit
    # approval. No retries, no fake empty result; keep the raw operation open.
    "sell_leads.*": CapabilityPolicy(
        availability=AVAILABILITY_LIMITED_RELEASE,
        required_scopes=["sell.leads"],
        production_approval="eBay business unit (Limited Release)",
        note=(
            "Leads is a Limited Release API available only to developers "
            "approved by an eBay business unit. A 500 'Access is denied' means "
            "this account lacks the approval/scope; do not retry."
        ),
        retry=False,
        references=["https://developer.ebay.com/develop/api/sell/leads_api"],
    ),
    # eDIS: account-ineligible (Greater-China sellers with an active eDIS
    # account). A 401 'user account is not allowed' is account_not_eligible, not
    # token_expired; OAuth re-consent is NOT the remedy.
    "sell_edelivery_international_shipping.*": CapabilityPolicy(
        availability=AVAILABILITY_ACCOUNT_RESTRICTED,
        account_requirement="Greater-China seller with an active eDIS account",
        note=(
            "eDIS is available only to Greater-China-based sellers with an active "
            "eDIS account. A 401 means the account is ineligible, not that the "
            "token expired; re-consent will not help."
        ),
        retry=False,
        references=[
            "https://developer.ebay.com/api-docs/sell/edelivery_international_shipping/static/overview.html"
        ],
    ),
    # VeRO: scope is not membership. commerce.vero is configured but the
    # API requires Verified Rights Owner Program membership; a 403 'subscription
    # missing' is membership_restricted and must not be retried.
    "commerce_vero.*": CapabilityPolicy(
        availability=AVAILABILITY_MEMBERSHIP_RESTRICTED,
        required_scopes=["commerce.vero"],
        membership="Verified Rights Owner Program",
        note=(
            "The commerce.vero scope is necessary but not sufficient: the VeRO "
            "API requires Verified Rights Owner Program membership. A 403 "
            "'subscription missing' is a membership failure, not a scope bug."
        ),
        retry=False,
        references=["https://developer.ebay.com/develop/api/sell/vero_public_apis"],
    ),
    # Buy bulk/Deal/Marketing are production-entitlement surfaces. Single
    # Browse getItem/search work for this account; bulk/Deal/Marketing do not and
    # return 403. Don't infer all Buy APIs work from one Browse read.
    "buy_browse.getItems": CapabilityPolicy(
        availability=AVAILABILITY_PRODUCTION_ENTITLEMENT,
        production_approval="eBay Buy partner application",
        note=(
            "Bulk Browse getItems is a production-entitlement surface; a 403 "
            "means partner approval/contract is missing, not a malformed request."
        ),
        retry=False,
        references=["https://developer.ebay.com/api-docs/buy/buy-requirements.html"],
    ),
    "buy_deal.*": CapabilityPolicy(
        availability=AVAILABILITY_PRODUCTION_ENTITLEMENT,
        production_approval="eBay Buy partner application",
        retry=False,
        references=["https://developer.ebay.com/api-docs/buy/buy-requirements.html"],
    ),
    "buy_marketing.*": CapabilityPolicy(
        availability=AVAILABILITY_PRODUCTION_ENTITLEMENT,
        production_approval="eBay Buy partner application (Beta)",
        note=(
            "Buy Marketing is a restricted Beta requiring approvals/contracts; a "
            "403 reflects entitlement, not a request bug."
        ),
        retry=False,
        references=[
            "https://developer.ebay.com/api-docs/buy/marketing/overview.html",
            "https://developer.ebay.com/api-docs/buy/buy-requirements.html",
        ],
    ),
    # Compliance PBSE was rolled back; PRODUCT_ADOPTION 404s for everyone
    # with normal inventory access. Keep the operation callable for completeness
    # but mark it stale/not-applicable; do not guide a listing repair from it.
    "sell_compliance.getListingViolations": CapabilityPolicy(
        availability=AVAILABILITY_STALE,
        note=(
            "The Product-Based Shopping Experience mandate was rolled back; "
            "PRODUCT_ADOPTION is not currently applicable and returns 404 for "
            "accounts with normal inventory access. Do not repair listings from "
            "this unless a live response contains actual violations."
        ),
        retry=False,
        references=[
            "https://developer.ebay.com/api-docs/sell/compliance/resources/methods",
            "https://developer.ebay.com/api-docs/sell/static/inventory/pbse-compliance-reason-codes.html",
        ],
    ),
    "sell_compliance.getListingViolationsSummary": CapabilityPolicy(
        availability=AVAILABILITY_STALE,
        retry=False,
        references=[
            "https://developer.ebay.com/api-docs/sell/compliance/resources/methods"
        ],
    ),
}

# Operations verified to work for a standard seller account (single-item Browse,
# Browse search) — surfaced as ``available`` so an agent does not infer all Buy
# APIs are blocked from the bulk/Deal/Marketing 403s.
_AVAILABLE: dict[str, CapabilityPolicy] = {
    "buy_browse.getItem": CapabilityPolicy(
        availability=AVAILABILITY_AVAILABLE,
        note="Single-item Browse read works for a standard seller account.",
    ),
    "buy_browse.search": CapabilityPolicy(
        availability=AVAILABILITY_AVAILABLE,
        note="Browse search works for a standard seller account.",
    ),
}


def capability_for(operation_key: str) -> CapabilityPolicy | None:
    """Resolve the policy for an operation: exact key, then service wildcard."""
    if operation_key in _POLICY:
        return _POLICY[operation_key]
    if operation_key in _AVAILABLE:
        return _AVAILABLE[operation_key]
    service = operation_key.split(".", 1)[0]
    wildcard = f"{service}.*"
    if wildcard in _POLICY:
        return _POLICY[wildcard]
    return None


def hint_for_failure(operation_key: str, status: int) -> str | None:
    """An operation-specific remediation hint for a failed call.

    ``_AVAILABLE`` entries are availability *annotations*
    ("this works for a standard account"), not failure remedies, so a failure on
    an available surface must not echo them — a legitimate 404 on
    ``buy_browse.getItem`` would otherwise get "Single-item Browse read works",
    which is irrelevant to a not-found. Only restricted/broken policies
    contribute a hint, and when a policy has no curated ``note`` we synthesize one
    from its availability/production/membership labels so e.g. a Buy Deal 403
    still names the entitlement gap.
    """
    policy = capability_for(operation_key)
    if policy is None or policy.availability == AVAILABILITY_AVAILABLE:
        return None
    # Only surface the hint when the status is plausibly the policy's failure
    # mode, so a 400 invalid_request on Leads is not rewritten as an approval
    # problem.
    if status not in {401, 403, 404, 500}:
        return None
    if policy.note:
        return policy.note
    return _synthesize_hint(policy)


def _synthesize_hint(policy: CapabilityPolicy) -> str | None:
    """Build a hint from a policy's labels when no curated note exists."""
    availability = policy.availability
    if availability == AVAILABILITY_LIMITED_RELEASE:
        return "Limited Release API; approval/scope is required and a failure is not a request bug."
    if availability == AVAILABILITY_PRODUCTION_ENTITLEMENT:
        return (
            "Production-entitlement surface; a failure reflects missing partner "
            "approval/contract, not a malformed request."
        )
    if availability == AVAILABILITY_MEMBERSHIP_RESTRICTED:
        return "Membership-restricted surface; the scope is necessary but not sufficient."
    if availability == AVAILABILITY_ACCOUNT_RESTRICTED:
        return "Account-restricted surface; this account is ineligible."
    if availability == AVAILABILITY_STALE:
        return (
            "Stale/not-applicable surface; do not repair from this unless a live "
            "response has violations."
        )
    if availability == AVAILABILITY_UPSTREAM_FAILURE:
        return "Upstream failure observed for this account; retry later."
    return None


__all__ = [
    "AVAILABILITY_ACCOUNT_RESTRICTED",
    "AVAILABILITY_AVAILABLE",
    "AVAILABILITY_LIMITED_RELEASE",
    "AVAILABILITY_MEMBERSHIP_RESTRICTED",
    "AVAILABILITY_PRODUCTION_ENTITLEMENT",
    "AVAILABILITY_STALE",
    "AVAILABILITY_UPSTREAM_FAILURE",
    "CapabilityPolicy",
    "capability_for",
    "hint_for_failure",
]
