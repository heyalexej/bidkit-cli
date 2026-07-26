"""Stable error classification for LLM ergonomics (error taxonomy).

The raw status/message pair is not enough for an agent to decide what to do.
Every failed operation must return a stable, machine-readable ``classification``
plus a short human/LLM hint, so retries and remediation are deterministic
instead of guesswork.

Canonical classifications:

============== ================ ================================================= ========
classification  status           meaning                                            retry?
============== ================ ================================================= ========
invalid_request  400              Required input, enum, pagination, or filter wrong   No
unauthenticated  401 (default)    Token expired/insufficient; refresh or re-consent    Yes
account_not_eligible 401 (policy)  User cannot call this account-restricted product    No
not_found        404              Resource/route absent, stale, or not applicable     No
capability_not_granted 403       Scope, membership, partner approval, or sub missing No
upstream_error   500              eBay endpoint failed after a valid request          Bounded
rate_limited     429              eBay requested backoff                              Yes
transport_error  timeout/network  Request did not complete reliably                   Bounded
============== ================ ================================================= ========

Key discipline: a 500 whose body contains "Access is denied"
must NOT become ``capability_not_granted``. The HTTP status is the primary
signal; the body is a hint, never an override. A 500 is always an upstream
failure with bounded retry, even when its prose mentions access. This keeps the
classification stable and prevents infinite retry loops on a genuine
authorization problem that happens to surface as a 500.

The overwhelmingly common eBay 401 is an expired/insufficient
user token, whose remedy IS to refresh/re-consent. Mapping every 401 to
``account_not_eligible`` steered agents away from that remedy. The default 401
is now ``unauthenticated`` (retry after refresh); ``account_not_eligible`` is
reserved for a capability-policy match (eDIS), where re-consent genuinely does
not help.

HTML bodies (the awaiting-feedback 500 returns an HTML error page) are
normalized into a bounded ``upstream_error`` object: status, operation,
request/correlation id, content type, and a short sanitized preview — never the
full page — so an agent gets structured input instead of scraping prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Any

# Maximum bytes of a non-JSON body to retain in the normalized preview. Keeps the
# error payload token-bounded and free of the full HTML/stack-trace page.
_BODY_PREVIEW_BYTES = 280


@dataclass(frozen=True)
class ErrorClassification:
    """The stable, machine-readable result of classifying one failed call."""

    kind: str
    retry: bool
    retry_after: float | None = None  # seconds; honored for rate_limited (Retry-After)
    hint: str | None = None
    normalized_body: dict[str, Any] | None = None


def classify_response(
    status: int | None,
    *,
    operation: str | None = None,
    body: Any = None,
    content_type: str = "",
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> ErrorClassification:
    """Classify a raw HTTP response (the dispatch path uses this).

    ``body`` may be parsed JSON, raw text/bytes, or None. Non-JSON bodies are
    normalized into a bounded preview so an HTML error page never reaches an
    agent verbatim. The classification is driven by the HTTP status; the body is
    consulted only for the rate-limit ``Retry-After`` header and to enrich the
    hint, never to override the status-derived kind.
    """
    # Case-insensitive header lookup: httpx2 lowercases header names, but this is
    # a public entry point and a caller passing a plain dict with "Retry-After"
    # must not silently lose the backoff.
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    retry_after = _retry_after(headers.get("retry-after"))
    if status is None:
        return ErrorClassification(
            kind="transport_error", retry=True, retry_after=retry_after,
            hint="The request did not complete reliably (timeout/network). "
                 "Retry with bounded backoff; re-read state before retrying a write.",
        )
    if status == 400:
        return ErrorClassification(
            kind="invalid_request", retry=False,
            hint=_body_hint(body),
            normalized_body=_normalize_body(body, content_type, status, operation, request_id),
        )
    if status == 401:
        # The default 401 is an expired/insufficient user token whose remedy is
        # to refresh or re-consent — so it is retriable as ``unauthenticated``.
        # ``account_not_eligible`` is reserved for surfaces whose capability
        # policy marks the *account itself* restricted (e.g. eDIS): there the
        # account genuinely cannot call the product and re-consent will not
        # help. A merely limited-release/entitlement surface can still 401 for
        # the ordinary expired-token reason, so its policy note is appended to
        # the unauthenticated hint instead of overriding the classification —
        # telling an agent "do not re-authenticate" on an expired token steers
        # it away from the fix.
        normalized = _normalize_body(body, content_type, status, operation, request_id)
        policy_hint = _policy_hint(operation, status)
        if _account_restricted(operation):
            return ErrorClassification(
                kind="account_not_eligible", retry=False,
                hint=policy_hint,
                normalized_body=normalized,
            )
        hint = (
            "The access token is expired or insufficient. Refresh the token "
            "(`bidkit auth login`) or re-consent, then retry."
        )
        if policy_hint:
            hint = f"{hint} Note: {policy_hint}"
        return ErrorClassification(
            kind="unauthenticated", retry=True, retry_after=retry_after,
            hint=hint,
            normalized_body=normalized,
        )
    if status == 403:
        return ErrorClassification(
            kind="capability_not_granted", retry=False,
            hint=_policy_hint(operation, status)
            or "A scope, membership, partner approval, or subscription is missing; "
               "do not retry — re-grant consent or request access.",
            normalized_body=_normalize_body(body, content_type, status, operation, request_id),
        )
    if status == 404:
        return ErrorClassification(
            kind="not_found", retry=False,
            hint=_policy_hint(operation, status)
            or "The resource/route is absent, stale, or no longer applicable; do not retry.",
            normalized_body=_normalize_body(body, content_type, status, operation, request_id),
        )
    if status == 429:
        return ErrorClassification(
            kind="rate_limited", retry=True, retry_after=retry_after,
            hint="eBay requested backoff; obey Retry-After before retrying.",
            normalized_body=_normalize_body(body, content_type, status, operation, request_id),
        )
    if 500 <= status < 600:
        # A 500 is ALWAYS upstream_error with bounded retry, even when its
        # prose says "Access is denied". The endpoint family / scope /
        # neighboring-success context matters and is encoded in the policy hint,
        # not in an ad-hoc body rewrite of the classification.
        return ErrorClassification(
            kind="upstream_error", retry=True, retry_after=retry_after,
            hint=_policy_hint(operation, status)
            or "eBay failed this request after receiving it; retry with bounded "
               "exponential backoff and jitter, and stop after a few attempts.",
            normalized_body=_normalize_body(body, content_type, status, operation, request_id),
        )
    # Any other 4xx we did not name: treat as a non-retriable invalid request.
    return ErrorClassification(
        kind="invalid_request", retry=False,
        hint=_body_hint(body),
        normalized_body=_normalize_body(body, content_type, status, operation, request_id),
    )


def _body_hint(body: Any) -> str | None:
    """Surface a short, sanitized hint from a JSON error body, if any."""
    payload = _first_error(body)
    if not isinstance(payload, dict):
        return None
    message = payload.get("message") or payload.get("longMessage")
    if isinstance(message, str) and message.strip():
        return _sanitize_preview(message, 200)
    return None


def _normalize_body(
    body: Any, content_type: str, status: int, operation: str | None,
    request_id: str | None,
) -> dict[str, Any] | None:
    """Bound a non-JSON (or unstructured) body into a stable preview.

    Returns None for a clean JSON body that ``_body_hint`` already summarized.
    For HTML/text/bytes we keep a short sanitized preview plus the operation and
    request id so an agent has structured input instead of scraping the page.
    """
    if body is None:
        return None
    # Already-parsed JSON eBay envelope: keep only the first error id/message,
    # never the whole body (which can be large).
    if isinstance(body, (dict, list)):
        return None
    text = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
    return {
        "status": status,
        "operation": operation,
        "request_id": request_id,
        "content_type": (content_type or "").split(";", 1)[0].strip() or None,
        "body_preview": _sanitize_preview(text, _BODY_PREVIEW_BYTES),
    }


def _first_error(body: Any) -> dict[str, Any] | None:
    if isinstance(body, dict):
        errors = body.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            return errors[0]
        return body
    if isinstance(body, list) and body and isinstance(body[0], dict):
        return body[0]
    return None


def _sanitize_preview(text: str, limit: int) -> str:
    """Collapse whitespace and truncate to ``limit`` chars for a bounded hint."""
    import re

    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header (delta-seconds or HTTP-date) into seconds."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    # HTTP-date form: best-effort parse; fall back to None. Note
    # parsedate_to_datetime raises on malformed input (it does not return None).
    from email.utils import parsedate_to_datetime

    try:
        from datetime import datetime

        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return max(0.0, (when - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def _policy_hint(operation: str | None, status: int) -> str | None:
    """Operation-specific remediation hint from the capability policy."""
    if operation is None:
        return None
    from .capability_policy import hint_for_failure

    return hint_for_failure(operation, status)


def _account_restricted(operation: str | None) -> bool:
    """True when the capability policy marks the account itself restricted.

    Only these surfaces justify ``account_not_eligible`` on a 401 — every other
    policy label (limited release, entitlement, membership) can coexist with an
    ordinary expired-token 401.
    """
    if operation is None:
        return False
    from .capability_policy import AVAILABILITY_ACCOUNT_RESTRICTED, capability_for

    policy = capability_for(operation)
    return policy is not None and policy.availability == AVAILABILITY_ACCOUNT_RESTRICTED


__all__ = [
    "ErrorClassification",
    "classify_response",
]
