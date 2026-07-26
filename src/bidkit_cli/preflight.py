"""Local preflight checks run before a request reaches eBay.

The generated OpenAPI validation cannot know eBay's marketplace-specific limits
or dynamic taxonomy requirements, so a malformed listing only fails after
dispatch. This module catches the failures most often hit in practice:

* Inventory-item title over the marketplace limit (error 25718).
* Inventory-item ``product.imageUrls`` over the 24-image boundary.

Both are validated against the *resolved* marketplace, so an EBAY_DE title of 81
characters is rejected locally with the exact limit in the message.
"""

from __future__ import annotations

from typing import Any

from .errors import ValidationError_
from .locales import MAX_IMAGE_URLS, title_limit
from .manifest import OperationRecord


def preflight(
    operation: OperationRecord,
    *,
    body: Any,
    marketplace_id: str | None,
) -> None:
    """Run operation-specific preflight checks; raise ValidationError_ on failure."""
    if operation.key == "sell_inventory.createOrReplaceInventoryItem":
        _preflight_inventory_item(body, marketplace_id=marketplace_id)


def _preflight_inventory_item(body: Any, *, marketplace_id: str | None) -> None:
    data = _as_dict(body)
    if data is None:
        return
    product = _as_dict(data.get("product"))
    if product is None:
        return
    _check_title(product, marketplace_id=marketplace_id, op_key="createOrReplaceInventoryItem")
    _check_image_urls(product, op_key="createOrReplaceInventoryItem")


def _as_dict(value: Any) -> dict[str, Any] | None:
    """Normalize a validated body (dict or Pydantic model) to a plain dict."""
    if isinstance(value, dict):
        return value
    try:
        from pydantic import BaseModel
    except ImportError:  # pragma: no cover
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True)
    return None


def _check_title(product: dict[str, Any], *, marketplace_id: str | None, op_key: str) -> None:
    title = product.get("title")
    if not isinstance(title, str):
        return
    limit = title_limit(marketplace_id)
    if len(title) > limit:
        raise ValidationError_(
            f"inventory item title is {len(title)} characters, exceeding the "
            f"{marketplace_id or 'marketplace'} limit of {limit} (eBay error 25718)",
            operation=op_key,
            details=[{"field": "product.title", "limit": limit, "length": len(title)}],
        )


def _check_image_urls(product: dict[str, Any], *, op_key: str) -> None:
    urls = product.get("imageUrls")
    if not isinstance(urls, list):
        return
    if len(urls) > MAX_IMAGE_URLS:
        raise ValidationError_(
            f"inventory item has {len(urls)} image URLs, exceeding eBay's "
            f"limit of {MAX_IMAGE_URLS} per item",
            operation=op_key,
            details=[
                {"field": "product.imageUrls", "limit": MAX_IMAGE_URLS, "count": len(urls)}
            ],
        )
