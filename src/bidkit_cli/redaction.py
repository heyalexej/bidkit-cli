"""Secret-redaction policy shared by every output mode.

One case-insensitive policy decides whether a header or query name is sensitive,
so dry-run, raw response headers, ``--include-meta``, and diagnostics can never
disagree. The rule intentionally over-matches a small set of names: a false
positive (showing ``<redacted>`` for a benign header) is cheap, while a false
negative (printing a live token) is not.

Applied to header names and query-parameter *names*. Request bodies use the
structural ``_shape()`` preview in dispatch, which already redacts by key.
"""

from __future__ import annotations

from typing import Any

# Substrings that mark a name as sensitive wherever they appear (case-insensitive).
# ``key`` is intentionally *not* a substring (too many benign eBay header names
# contain "key"); ``api-key``/``apikey`` are specific enough.
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "apikey",
    "api_key",
    "api-key",
    "authorization",
    "signature",
)

# Exact (lower-cased) names that do not contain any substring above but must
# still be treated as secrets.
_SENSITIVE_EXACT: frozenset[str] = frozenset({
    "cookie",
    "set-cookie",
    # eBay end-user context header can carry user attribution; never echo it.
    "x-ebay-c-enduserctx",
})

_REDACTED = "<redacted>"


def is_sensitive_name(name: str) -> bool:
    """True if a header/query name should never have its value printed."""
    lowered = name.lower()
    if lowered in _SENSITIVE_EXACT:
        return True
    return any(part in lowered for part in _SENSITIVE_SUBSTRINGS)


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``mapping`` with every sensitive value replaced.

    Used for the dry-run header and query previews. Array values under a
    sensitive name are redacted wholesale (the whole list becomes the marker).
    """
    return {
        key: (_REDACTED if is_sensitive_name(key) else value)
        for key, value in mapping.items()
    }
