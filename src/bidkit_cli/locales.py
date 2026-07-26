"""Marketplace → locale and listing-limit tables.

The generated inventory command does not expose the ``Content-Language`` control
eBay uses to validate German listings: a plain EBAY_DE ``create-or-replace``
defaults to ``en-US`` and fails the German locale check. This module gives the
CLI a first-class, *offline* mapping so an EBAY_DE workflow works without the
``--allow-unknown-params --header`` escape hatch.

It also carries the marketplace-specific listing limits the API only reports at
dispatch time (EBAY_DE title limit is 80 characters → error 25718), so the
CLI can preflight a request body before it reaches eBay.
"""

from __future__ import annotations

from typing import Any

# eBay marketplace → (content_language, accept_language). Sourced from eBay's
# documented marketplaces; kept to the locales the seller workflow needs. An
# unknown marketplace maps to None so callers can decide whether to fall back.
MARKETPLACE_LOCALES: dict[str, tuple[str, str]] = {
    "EBAY_AT": ("de-AT", "de-AT"),
    "EBAY_AU": ("en-AU", "en-AU"),
    "EBAY_BE": ("nl-BE", "nl-BE"),
    "EBAY_CA": ("en-CA", "en-CA"),
    "EBAY_CH": ("de-CH", "de-CH"),
    "EBAY_DE": ("de-DE", "de-DE"),
    "EBAY_ES": ("es-ES", "es-ES"),
    "EBAY_FR": ("fr-FR", "fr-FR"),
    "EBAY_GB": ("en-GB", "en-GB"),
    "EBAY_HK": ("en-HK", "en-HK"),
    "EBAY_IE": ("en-IE", "en-IE"),
    "EBAY_IT": ("it-IT", "it-IT"),
    "EBAY_NL": ("nl-NL", "nl-NL"),
    "EBAY_PL": ("pl-PL", "pl-PL"),
    "EBAY_US": ("en-US", "en-US"),
}

# The OAuth scope that works with the client-credentials grant. Every other
# configured scope is user-only; including them in the client-token request
# makes a healthy app keyset look broken (``invalid_scope``).
CLIENT_CREDENTIALS_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Title length limits by marketplace. The API rejects an over-limit title
# with error 25718 only after dispatch; preflighting avoids a wasted round trip.
# Defaults are conservative; unknown marketplaces fall back to 80.
MARKETPLACE_TITLE_LIMITS: dict[str, int] = {
    "EBAY_DE": 80,
    "EBAY_AT": 80,
    "EBAY_CH": 80,
    "EBAY_US": 80,
    "EBAY_GB": 80,
    "EBAY_AU": 80,
    "EBAY_FR": 100,
    "EBAY_IT": 100,
    "EBAY_ES": 100,
    "EBAY_NL": 100,
    "EBAY_BE": 100,
    "EBAY_IE": 80,
    "EBAY_CA": 80,
    "EBAY_PL": 100,
}
DEFAULT_TITLE_LIMIT = 80

# eBay inventory items cap the number of image URLs at 24. The API silently
# rejects a larger set; preflighting surfaces the boundary locally.
MAX_IMAGE_URLS = 24


def locale_for(marketplace_id: str | None) -> tuple[str, str] | None:
    """Return ``(content_language, accept_language)`` for a marketplace, or None."""
    if not marketplace_id:
        return None
    return MARKETPLACE_LOCALES.get(marketplace_id)


def title_limit(marketplace_id: str | None) -> int:
    """The maximum inventory-item title length for a marketplace."""
    if marketplace_id and marketplace_id in MARKETPLACE_TITLE_LIMITS:
        return MARKETPLACE_TITLE_LIMITS[marketplace_id]
    return DEFAULT_TITLE_LIMIT


def derive_languages(
    *,
    marketplace_id: str | None,
    marketplace_locale: bool,
    content_language: str | None,
    accept_language: str | None,
    config_content_language: str | None,
    config_accept_language: str | None,
) -> tuple[str | None, str | None]:
    """Resolve the effective (content_language, accept_language).

    Precedence (highest first):
      1. explicit CLI ``--content-language`` / ``--accept-language``;
      2. ``--marketplace-locale`` derivation from the marketplace table;
      3. the config file's values;
      4. None (the SDK then applies its own ``en-US`` default).
    """
    derived = locale_for(marketplace_id) if marketplace_locale else None
    content = (
        content_language
        or (derived[0] if derived else None)
        or config_content_language
    )
    accept = (
        accept_language
        or (derived[1] if derived else None)
        or config_accept_language
    )
    return content, accept


def locales_table() -> list[dict[str, Any]]:
    """A JSON-friendly view of the marketplace→locale table for ``config locales``."""
    rows: list[dict[str, Any]] = []
    for marketplace_id, (content, accept) in MARKETPLACE_LOCALES.items():
        rows.append(
            {
                "marketplace_id": marketplace_id,
                "content_language": content,
                "accept_language": accept,
                "title_limit": title_limit(marketplace_id),
            }
        )
    return rows
