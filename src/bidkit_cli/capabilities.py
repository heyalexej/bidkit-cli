"""Capability diagnostics and data-domain map.

eBay splits "things this account did" across *different data domains* that the
generated OAS surface does not label:

* **seller sales** — ``sell_fulfillment`` (orders where THIS account is the
  seller) and ``sell_finances`` (seller fees/payouts);
* **member purchases** — purchases made BY this account. There is no member
  purchase-order operation in the current ``buy_order`` OAS surface (it covers
  guest checkout only) and the configured OAuth scopes contain no buyer-order
  scope, so member purchase history is *unavailable* on this surface;
* **guest checkout** — ``buy_order`` guest session/purchase-order operations;
* **feedback** — ``commerce_feedback``.

An LLM searching ``api search order`` otherwise picks ``sell_fulfillment.getOrders``
and reports *sales* as *purchases*. This module labels services by domain, so
discovery can warn, and exposes a single honest capability diagnostic for member
purchase history instead of letting an agent infer "no purchases" from a
logged-out page.
"""

from __future__ import annotations

from typing import Any

# service_key -> data domain label. Hand-curated: the OAS does not encode which
# side of a transaction an account is on. Every key must exist in the manifest
# (see :func:`validate_domain_map`, exercised by the test suite), so a renamed
# service fails loudly.
SERVICE_DOMAINS: dict[str, str] = {
    # seller side
    "sell_fulfillment": "seller_sales",
    "sell_finances": "seller_sales",
    # guest checkout (buyer side, but non-member)
    "buy_order": "guest_checkout",
    # feedback
    "commerce_feedback": "feedback",
}

# Canonical domain metadata for display and the capability report.
DOMAINS: dict[str, dict[str, Any]] = {
    "seller_sales": {
        "label": "seller sales",
        "description": (
            "Orders where THIS account is the seller, plus seller fees, payouts, "
            "and transactions (sell_fulfillment / sell_finances)."
        ),
    },
    "member_purchases": {
        "label": "member purchases",
        "available": False,
        "reason": "No member-order OAS operation or granted buyer scope",
        "description": (
            "Purchases made BY this account. Not reachable from the current "
            "sell/buy OAS surface; buy_order covers guest checkout only."
        ),
    },
    "guest_checkout": {
        "label": "guest checkout",
        "description": (
            "Guest (non-member) checkout sessions and purchase orders (buy_order)."
        ),
    },
    "feedback": {
        "label": "feedback",
        "description": "Received/sent feedback (commerce_feedback).",
    },
}


def domain_for_service(service_key: str) -> str | None:
    """Return the data-domain label for a service key, or None if unlabeled."""
    return SERVICE_DOMAINS.get(service_key)


def member_purchase_capability(*, browser_cdp: str | None = None) -> dict[str, Any]:
    """The honest member-purchase-history capability report.

    Returns a machine-readable record an agent can act on. The current surface
    is unavailable (no member-order operation, no buyer scope); the report says
    so explicitly and never claims "no purchases". When a Chrome DevTools
    endpoint is supplied we record that an authenticated-browser fallback exists
    but is not attempted here, so an agent never infers absence from a logged-out
    page.
    """
    report: dict[str, Any] = {
        "capability": "member_purchase_history",
        "available": False,
        "reason": "No member-order OAS operation or granted buyer scope",
        "generated_surface": {
            "service": "buy_order",
            "operations": [
                "get-guest-checkout-session",
                "get-guest-purchase-order",
            ],
            "scope": "guest checkout only",
        },
        "seller_sales_distinct": (
            "sell_fulfillment.getOrders describes orders where this account is "
            "the SELLER, not purchases made by the account; do not use it to "
            "answer purchase-history questions."
        ),
        "browser_fallback": "requires_authenticated_ebay_session",
    }
    if browser_cdp:
        report["browser_cdp"] = browser_cdp
        report["browser_fallback_note"] = (
            "An authenticated Chrome session via --browser-cdp is the only "
            "fallback; it is NOT attempted here, and a redirect to sign-in must "
            "be reported as 'unavailable', never as 'no purchases'."
        )
    return report


def validate_domain_map(manifest_services: set[str]) -> list[str]:
    """Fail loudly if any domain-mapped service is absent from the manifest.

    Returns a list of human-readable warnings (empty when clean). Keeps the
    hand-curated domain map honest against upstream renames.
    """
    problems: list[str] = []
    for service_key in SERVICE_DOMAINS:
        if service_key not in manifest_services:
            problems.append(
                f"domain map references unknown service {service_key!r} "
                "(stale service key)"
            )
    return problems


__all__ = [
    "DOMAINS",
    "SERVICE_DOMAINS",
    "domain_for_service",
    "member_purchase_capability",
    "validate_domain_map",
]
