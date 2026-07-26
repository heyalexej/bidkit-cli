"""Stateful seller workflows the generated operations cannot express alone.

Three concerns that need CLI-level composition:

* **Replace-like PUTs** (``updateOffer``, ``createOrReplaceInventoryItem``):
  eBay treats the JSON body as a *full replacement*, so an omitted field reverts
  to an account/API default. :func:`merge_body` implements the read/merge/write
  wrapper so an LLM cannot accidentally drop ``listingPolicies`` or boolean flags.
* **Frontend propagation**: after a successful offer/inventory write the public
  listing page may lag the API by minutes and can be throttled (HTTP 403).
  :func:`verify_live` compares the API readback against the request with a
  recursive *subset* match, so normal server enrichment like
  ``allocationByFormat``/timestamps is not a false failure, and reports
  ``api_verified`` separately from ``frontend_verified`` (null — the public page
  is intentionally not polled) instead of implying immediate convergence.
* **Publish taxonomy errors**: ``publishOffer`` fails with error 25002 when a
  category-required aspect is missing. :func:`enrich_publish_error` turns that
  opaque error into an actionable hint naming the specific missing aspects
  (parsed from ``errors[].parameters``) and pointing at the taxonomy operation.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx2

from .context import CliContext
from .errors import UsageError
from .manifest import Manifest, OperationRecord


def _as_int(value: Any) -> int | None:
    """Best-effort int coercion; returns None when the value is not numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

# Replace-like PUTs and their GET read counterpart. Both share the same
# path template, so the read uses the same path params. Curated here (not
# generated) because "is this a replacement" is a behavior the OpenAPI surface
# does not encode.
REPLACE_LIKE_OPS: dict[str, str] = {
    "sell_inventory.updateOffer": "sell_inventory.getOffer",
    "sell_inventory.createOrReplaceInventoryItem": "sell_inventory.getInventoryItem",
}

REPLACE_LIKE_NOTE = (
    "treats the body as a full replacement: an omitted field reverts to the "
    "account/API default. Pass --merge to read the current state, apply only "
    "the fields you set, and PUT the merged body."
)


def is_replace_like(operation: OperationRecord) -> bool:
    return operation.key in REPLACE_LIKE_OPS


def read_counterpart(manifest: Manifest, operation: OperationRecord) -> OperationRecord | None:
    key = REPLACE_LIKE_OPS.get(operation.key)
    if key is None:
        return None
    return manifest.get(key)


def deep_merge(base: Any, patch: Any) -> Any:
    """Recursively merge ``patch`` onto ``base``; patch wins at every leaf.

    For dicts the union of keys is merged recursively; for lists/ scalars the
    patch replaces the base outright (offer ``listingPolicies`` IDs and image
    URL lists are *not* element-wise merged — the caller's full list is the
    source of truth).
    """
    base = _to_dict(base)
    patch = _to_dict(patch)
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            merged[key] = deep_merge(base.get(key), value)
        return merged
    return patch


def _to_dict(value: Any) -> Any:
    """Dump a Pydantic model to a plain dict (by alias, excluding unset Nones).

    ``exclude_none`` matters: a model validated from a partial body has every
    optional field set to None, and merging that would stomp the current state
    with nulls. Only fields the caller actually set should count as the patch.
    """
    try:
        from pydantic import BaseModel
    except ImportError:  # pragma: no cover
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    return value


def merge_body(
    context: CliContext,
    operation: OperationRecord,
    path_params: dict[str, str],
    body: Any,
) -> Any:
    """Fetch the current state and merge the provided body over it.

    The read counterpart is dispatched read-only through the normal path, so it
    shares auth, retry, and redaction. A 404 on the read is treated as "no
    existing state" and the provided body passes through unchanged (this is the
    create half of create-or-replace).
    """
    manifest = context.manifest
    read_op = read_counterpart(manifest, operation)
    if read_op is None:
        raise UsageError(f"{operation.key} has no read counterpart for --merge")
    from .dispatch import resolve_resource

    client = context.client
    resource = resolve_resource(client, manifest.service(read_op.service_key))
    path_args = [path_params[p.wire_name] for p in read_op.path_params]
    method = getattr(resource, read_op.python_method)
    current = method(*path_args, raw_response=True)
    if isinstance(current, httpx2.Response):
        if current.status_code == 404:
            return body  # nothing to merge over (the "create" case)
        if current.status_code >= 400:
            from bidkit.errors import EbayAPIError

            from .errors import ApiError

            api_err = EbayAPIError.from_response(current)
            raise ApiError(
                str(api_err),
                status=api_err.status_code,
                operation=read_op.key,
                request_id=api_err.request_id,
                details=[api_err.payload] if api_err.payload is not None else None,
                hint=(
                    f"--merge could not read current state via {read_op.key}; "
                    "remote state is unchanged, but the merge was aborted."
                ),
            ) from api_err
        content_type = current.headers.get("content-type", "")
        if "json" in content_type:
            import orjson

            current = orjson.loads(current.content) if current.content else {}
        else:
            current = None
    if body is None:
        return current
    return deep_merge(current, body)


# ---------------------------------------------------------------------------
# Frontend propagation verification
# ---------------------------------------------------------------------------

# Fields whose change an --verify-live readback should compare. Title/images are
# nested on the inventory item (product.*); offer price/description are top
# level. We compare everything present in the request body against the read.
def _request_fields(body: Any) -> dict[str, Any]:
    data = _to_dict(body)
    if not isinstance(data, dict):
        return {}
    flat: dict[str, Any] = {}
    for key, value in data.items():
        flat[key] = value
    # Unwrap the inventory product wrapper so a title/image change is visible.
    product = data.get("product") if isinstance(data.get("product"), dict) else None
    if product:
        for key in ("title", "imageUrls", "description", "aspects", "brand"):
            if key in product:
                flat[f"product.{key}"] = product[key]
    return flat


def _is_subset(requested: Any, observed: Any) -> bool:
    """True if ``requested`` is fully contained in ``observed``.

    Dicts compare as a *recursive subset*: the server legitimately enriches a
    write with derived fields (e.g. ``availability.allocationByFormat``, server
    timestamps), so an observed dict that is a strict superset of the requested
    one still counts as a match. Lists compare exactly — image order and list
    replacement are meaningful, so a reordering or partial list is a real
    mismatch. Scalars compare for equality. A requested dict against an absent
    (``None``) observed value is a real mismatch, distinct from enrichment.
    """
    if isinstance(requested, dict):
        if not isinstance(observed, dict):
            return False
        return all(
            key in observed and _is_subset(value, observed[key])
            for key, value in requested.items()
        )
    if isinstance(requested, list):
        if not isinstance(observed, list):
            return False
        return [str(item) for item in requested] == [str(item) for item in observed]
    return requested == observed


def verify_live(
    context: CliContext,
    operation: OperationRecord,
    path_params: dict[str, str],
    body: Any,
    *,
    wait_seconds: float,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    """Poll the API readback after a write and report convergence.

    Compares the requested fields against the API readback using a recursive
    *subset* match, so normal server enrichment (``allocationByFormat``,
    timestamps) no longer causes a false failure. The report clearly separates
    ``api_verified`` (the readback result) from ``frontend_verified`` (the public
    listing page, which is intentionally *not* polled here and may lag the API
    by minutes / be throttled). ``verified`` is kept as a backwards-compatible
    alias of ``api_verified``.
    """
    requested = _request_fields(body)
    if not requested:
        return _report(api_verified=False, reason="no comparable fields in the request body")
    read_op = read_counterpart(context.manifest, operation)
    if read_op is None:
        return _report(
            api_verified=False,
            reason=f"{operation.key} has no API readback counterpart",
        )
    from .dispatch import resolve_resource

    client = context.client
    resource = resolve_resource(client, context.manifest.service(read_op.service_key))
    method = getattr(resource, read_op.python_method)
    path_args = [path_params[p.wire_name] for p in read_op.path_params]

    deadline = time.monotonic() + wait_seconds
    attempts = 0
    matched: list[str] = []
    unmatched: list[str] = []
    server_added: list[str] = []
    # Pass the raw request body so ``_compare`` can compute server-added
    # *paths* with a generic recursive diff instead of the old selected-field
    # flattener that lost nested enrichment such as
    # ``availability.shipToLocationAvailability.allocationByFormat``.
    requested_body = _to_dict(body)
    while True:
        attempts += 1
        readback = method(*path_args, raw_response=True)
        observed = _readback_value(readback)
        matched, unmatched, server_added = _compare(requested_body, observed)
        if not unmatched or time.monotonic() >= deadline:
            break
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
    return {
        "api_verified": not unmatched,
        # The public listing page is not polled here; null = "not checked",
        # not "checked and failed".
        "frontend_verified": None,
        "verified": not unmatched,  # backwards-compatible alias of api_verified
        "attempts": attempts,
        "matched": matched,
        "unmatched": unmatched,
        "server_added_fields": server_added,
        "frontend_note": _FRONTEND_NOTE,
    }


def _report(*, api_verified: bool, reason: str) -> dict[str, Any]:
    return {
        "api_verified": api_verified,
        "frontend_verified": None,
        "verified": api_verified,  # backwards-compatible alias of api_verified
        "reason": reason,
        "frontend_note": _FRONTEND_NOTE,
    }


_FRONTEND_NOTE = (
    "This verifies API state only (the inventory/offer readback), not the "
    "public eBay listing page, which may lag the API by minutes and is often "
    "throttled for repeated checks (HTTP 403). frontend_verified is null "
    "because the public page is intentionally not polled here."
)


def _readback_value(readback: Any) -> Any:
    if isinstance(readback, httpx2.Response):
        content_type = readback.headers.get("content-type", "")
        if "json" in content_type and readback.content:
            import orjson

            return orjson.loads(readback.content)
        return None
    return readback


def _compare(
    requested_body: Any, observed: Any
) -> tuple[list[str], list[str], list[str]]:
    """Compare requested fields against the readback using a subset match.

    Returns ``(matched, unmatched, server_added_fields)``. ``matched``/
    ``unmatched`` use the field granularity an agent reads (top-level keys plus
    the unwrapped ``product.*`` fields), so a title or image change is visible.
    ``server_added_fields`` is computed by a generic recursive
    *path* diff (:func:`_added_paths`): dotted paths the readback returned that
    were not part of the request — e.g. ``sku``, ``locale``, and crucially the
    nested ``availability.shipToLocationAvailability.allocationByFormat`` that
    the previous selected-field flattener swallowed. Informational enrichment,
    never a failure.
    """
    requested = _request_fields(requested_body)
    observed_dict = observed if isinstance(observed, dict) else {}
    matched: list[str] = []
    unmatched: list[str] = []
    for field, value in requested.items():
        if _is_subset(value, _get_path(observed_dict, field)):
            matched.append(field)
        else:
            unmatched.append(field)
    server_added = sorted(_added_paths(_to_dict(requested_body), observed_dict))
    return matched, unmatched, server_added


def _added_paths(requested: Any, observed: Any, prefix: str = "") -> list[str]:
    """Dotted paths present in ``observed`` but absent from ``requested``.

    Dicts recurse; lists/scalars are leaves (image order and list replacement
    are meaningful, so a list is never exploded into index paths). When an
    entire subtree is absent from the request, its *root* path is reported once
    (collapsed) rather than every leaf — so
    ``availability.shipToLocationAvailability.allocationByFormat`` surfaces as a
    single diagnostic path instead of its ``auction``/``fixedPrice`` children.
    Paths are relative to the body root, matching the matched/unmatched fields.
    """
    if not isinstance(observed, dict):
        return []
    if not isinstance(requested, dict):
        # Requested is a leaf/list but observed is a dict: the whole observed
        # object is server-added structure; report each key as a path.
        return [_join_path(prefix, str(key)) for key in observed]
    added: list[str] = []
    for key, value in observed.items():
        path = _join_path(prefix, str(key))
        if key not in requested:
            added.append(path)  # entire subtree absent from the request
        else:
            added.extend(_added_paths(requested[key], value, path))
    return added


def _join_path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _get_path(observed: dict[str, Any], field: str) -> Any:
    if "." in field:
        head, _, rest = field.partition(".")
        nested = observed.get(head)
        return _get_path(nested, rest) if isinstance(nested, dict) else None
    return observed.get(field)


# ---------------------------------------------------------------------------
# public/Browse verification with stale-after-delete
# ---------------------------------------------------------------------------
#
# ``--verify-live`` only checks the *seller* API readback. A delete can succeed
# on the seller side while the public/Browse representation stays live for
# minutes. An LLM cannot distinguish "delete failed" from "delete succeeded,
# public state stale" from that report. ``verify_public`` is an explicit public
# verifier: Browse API is the primary machine check (with a Chrome DOM check as
# an optional extra), it never treats HTTP 403 as proof of absence, and it
# reports the honest, actionable combined state including ``stale_after_delete``.

# The full set of combined (seller + public) states an agent can act on
# without scraping prose. The lifecycle is modeled precisely: a withdrawn/
# deleted item keeps a durable public record (``itemEndDate`` in the past,
# ``OUT_OF_STOCK``, remaining 0) that is *not* a 404. ``not_listed`` models the
# user-facing "not listed anymore" (seller deleted AND public ended/
# unpurchasable); ``stale_after_delete`` is kept only for the transient window
# where the public representation still appears active (no end signal) while the
# seller record is already gone.
FRONTEND_STATES = (
    "not_checked",
    "not_yet_visible",
    "visible",
    "updated",
    "seller_active",   # seller present AND public active/purchasable
    "public_active",   # public active but seller record gone
    "public_ended",    # public record ended (past itemEndDate / OUT_OF_STOCK)
    "stale_after_delete",  # public still active-looking, seller deleted (transient)
    "not_listed",      # seller deleted AND public ended/unpurchasable
    "not_found",
    "blocked",
    "timeout",
)

# The public-listing classification surfaced separately so an agent can read
# the public side directly without re-deriving it from the combined state.
# ``retained`` is the durable ended record eBay keeps after a withdraw/delete
# (history), distinct from an active or 404 representation.
PUBLIC_LISTING_STATES = ("active", "ended", "retained", "not_found", "blocked")

# Expectations an agent can assert.
EXPECTATIONS = ("active", "visible", "not_listed", "not_found")


def normalize_item_id(listing_id: str) -> tuple[str, str]:
    """Normalize an eBay item id to the Browse RESTful form.

    Browse ``getItem`` requires the RESTful id ``v1|<legacy-id>|0``; passing a
    bare numeric legacy id returns a false 404. This central normalizer accepts
    either form at the CLI boundary and returns ``(browse_item_id,
    legacy_item_id)`` so callers can keep both values in their output and never
    hand a malformed id to ``buy_browse.getItem``.

    ``getItemByLegacyId`` exists as an alternate surface, but ``verify-public``
    and ``cleanup-report`` deliberately use ``getItem`` with the normalized id so
    content assertions and the public/state classification all run against the
    same representation an agent reads directly.
    """
    raw = (listing_id or "").strip()
    if not raw:
        raise UsageError("--listing-id is required")
    if raw.startswith("v1|"):
        parts = raw.split("|")
        legacy = parts[1] if len(parts) > 1 and parts[1] else raw
        return raw, legacy
    # Numeric (or otherwise non-RESTful) legacy id -> RESTful form. We do not
    # validate the digit run strictly: eBay legacy ids are numeric in practice,
    # but the RESTful wrapper is positional (``v1|<legacy>|0``), not
    # format-validated, so any legacy token round-trips safely.
    return f"v1|{raw}|0", raw


def legacy_from_item_id(item_id: str) -> str | None:
    """Extract the legacy numeric id from a RESTful ``v1|...|0`` form, else None."""
    if item_id and item_id.startswith("v1|"):
        parts = item_id.split("|")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return None

# Browse fields safe to retain in the last-observed summary. The Browse Item
# response carries large terms/privacy blobs (returnTerms, seller contact,
# responsiblePersons, productSafetyLabels, sellerCustomPolicies) and a long
# description; by default we keep only what an assertion or a human needs, never
# the legal-information blob.
_BROWSE_SUMMARY_FIELDS = (
    "itemId",
    "legacyItemId",
    "title",
    "categoryId",
    "condition",
    "buyingOptions",
    "listingMarketplaceId",
    "itemWebUrl",
    "topRatedBuyingExperience",
    "itemCreationDate",
    "itemEndDate",
)


def verify_public(
    context: CliContext,
    *,
    listing_id: str,
    sku: str | None = None,
    expect_browse: str = "visible",
    expect_title: str | None = None,
    expect_description_contains: str | None = None,
    expect_image_count: int | None = None,
    expect_price: str | None = None,
    expect_currency: str | None = None,
    expect_category_id: str | None = None,
    expect_buying_option: str | None = None,
    wait_seconds: float = 0.0,
    poll_interval: float = 15.0,
    full: bool = False,
) -> dict[str, Any]:
    """Poll the public/Browse representation of a listing.

    Browse API (``buy_browse.getItem``) is the primary machine check and is
    always called with the normalized RESTful id ``v1|<legacy>|0``, so a numeric
    ``--listing-id`` no longer produces a false 404. The seller API
    (``sell_inventory.getInventoryItem``) is consulted only when ``--sku`` is
    given so the report can say *deleted but public state stale / not listed*
    instead of leaving an agent to guess. The public lifecycle is modeled
    honestly: an ended/retained record is ``not_listed`` when the seller record
    is also gone, never a confusing 200.

    Output carries both ``legacy_item_id`` and ``browse_item_id`` plus a
    standalone ``public_listing_state``. ``content_verified`` is True only when
    a 200 was actually observed and every content assertion matched. By default
    the last-observed Browse item is summarized under a bounded allowlist so the
    large legal-information / seller-contact blob is never echoed; pass
    ``full=True`` to retain the raw Browse body for expert use.

    Never treat HTTP 403 as proof the item is absent: eBay throttles repeated
    public checks and returns 403, which we surface as ``blocked``.
    """
    if expect_browse not in EXPECTATIONS:
        raise UsageError(
            f"--expect must be one of {', '.join(EXPECTATIONS)}, got {expect_browse!r}"
        )
    browse_item_id, legacy_item_id = normalize_item_id(listing_id)
    manifest = context.manifest
    browse_op = manifest.get("buy_browse.getItem")
    if browse_op is None:
        return _public_report(
            listing_id=listing_id, legacy_item_id=legacy_item_id,
            browse_item_id=browse_item_id, api_state="not_checked",
            browse_state="not_checked", frontend_state="not_checked",
            attempts=0, elapsed_seconds=0.0, last_http_status=None,
            reason="buy_browse.getItem is not in the manifest", expect_browse=expect_browse,
        )

    from .dispatch import resolve_resource

    client = context.client
    browse_resource = resolve_resource(client, manifest.service(browse_op.service_key))
    browse_method = getattr(browse_resource, browse_op.python_method)

    inv_op = manifest.get("sell_inventory.getInventoryItem") if sku else None
    inv_resource = inv_method = None
    if inv_op is not None:
        inv_resource = resolve_resource(client, manifest.service(inv_op.service_key))
        inv_method = getattr(inv_resource, inv_op.python_method)

    deadline = time.monotonic() + wait_seconds
    start = time.monotonic()
    attempts = 0
    last_status: int | None = None
    browse_observed: dict[str, Any] | None = None
    browse_state = "not_checked"
    api_state = "not_checked"
    frontend_state = "not_checked"
    public_listing_state = "not_checked"
    met = False
    # Poll until the expectation is met or the wait budget is exhausted. We do
    # NOT early-stop on stale_after_delete/not_listed: they are honest *answers*
    # (and acceptable cleanup results), but if the caller gave a wait budget
    # they asked us to keep watching for full public convergence, so we honor it
    # and report the final state we actually saw.
    while True:
        attempts += 1
        response = browse_method(browse_item_id, raw_response=True)
        last_status = response.status_code if isinstance(response, httpx2.Response) else None
        browse_state, browse_observed = _classify_browse(response)
        # Determine the seller-side state lazily (it changes slowly, so one read
        # per attempt is enough and keeps the report truthful each poll).
        api_state = _seller_state(inv_method, sku) if inv_method is not None else "not_checked"
        frontend_state = _combine_frontend_state(api_state, browse_state)
        public_listing_state = _public_listing_state(browse_state, api_state)
        met = _expectation_met(frontend_state, browse_state, expect_browse)
        if met or time.monotonic() >= deadline:
            break
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))

    elapsed = time.monotonic() - start
    last_frontend_state = frontend_state
    # ``timeout`` is reserved for the case where we actively waited (budget > 0),
    # exhausted it, never met the expectation, AND the last read was a *transient*
    # state with no confident answer (blocked / not_yet_visible). A confident
    # honest state (visible / not_found / not_listed / public_ended /
    # stale_after_delete) is the answer even if it is not what we hoped for, so it
    # is never relabeled ``timeout``; a single check with --wait 0 is also never a
    # timeout.
    transient = {"not_yet_visible", "blocked"}
    timed_out = (
        wait_seconds > 0
        and not met
        and time.monotonic() >= deadline
        and frontend_state in transient
    )
    if timed_out:
        frontend_state = "timeout"
    assertions = _assert_browse_fields(
        browse_observed,
        expect_title=expect_title,
        expect_description_contains=expect_description_contains,
        expect_image_count=expect_image_count,
        expect_price=expect_price,
        expect_currency=expect_currency,
        expect_category_id=expect_category_id,
        expect_buying_option=expect_buying_option,
    )
    # content_verified: only True when a 200 was actually observed AND every
    # requested content assertion matched. A 404 caused by a malformed id (now
    # impossible thanks to normalization) or a blocked response is never
    # content_verified, even when there are no assertions to fail.
    saw_200 = browse_state in {"active", "ended"}
    content_verified = saw_200 and all(a["match"] for a in assertions) if assertions else saw_200
    return _public_report(
        listing_id=listing_id,
        legacy_item_id=legacy_item_id,
        browse_item_id=browse_item_id,
        api_state=api_state,
        browse_state=browse_state,
        frontend_state=frontend_state,
        public_listing_state=public_listing_state,
        attempts=attempts,
        elapsed_seconds=round(elapsed, 3),
        last_http_status=last_status,
        expect_browse=expect_browse,
        met_expectation=met,
        timed_out=timed_out,
        last_frontend_state=last_frontend_state,
        assertions=assertions,
        content_verified=content_verified,
        last_observed=browse_observed if full else _summarize_browse(browse_observed),
        last_observed_full=full,
        sku=sku,
    )


def _public_report(**fields: Any) -> dict[str, Any]:
    """Assemble the public-verification report with stable key ordering."""
    report: dict[str, Any] = {
        # Keep both identifiers so an agent can copy the right one. The
        # caller-supplied value is preserved verbatim under listing_id; the
        # normalized RESTful id and the derived legacy id are surfaced too.
        "listing_id": fields.get("listing_id"),
        "legacy_item_id": fields.get("legacy_item_id"),
        "browse_item_id": fields.get("browse_item_id"),
        "api_state": fields.get("api_state", "not_checked"),
        "browse_state": fields.get("browse_state", "not_checked"),
        "frontend_state": fields.get("frontend_state", "not_checked"),
        "public_listing_state": fields.get("public_listing_state", "not_checked"),
        "attempts": fields.get("attempts", 0),
        "elapsed_seconds": fields.get("elapsed_seconds", 0.0),
        "last_http_status": fields.get("last_http_status"),
        # Verification is read-only and idempotent: re-running it never changes
        # remote state, so a caller can always retry safely.
        "retry_safe": True,
        "expected": fields.get("expect_browse"),
        "met_expectation": fields.get("met_expectation", False),
        "timed_out": fields.get("timed_out", False),
    }
    if fields.get("last_frontend_state") and fields.get("timed_out"):
        # When the top-level state was relabeled ``timeout``, keep the honest
        # last classification underneath so an agent still sees "blocked" vs
        # "not_yet_visible" instead of losing it.
        report["last_frontend_state"] = fields["last_frontend_state"]
    if "reason" in fields:
        report["reason"] = fields["reason"]
    if "assertions" in fields:
        report["assertions"] = fields["assertions"]
    if "content_verified" in fields:
        report["content_verified"] = fields["content_verified"]
    if "last_observed" in fields:
        report["last_observed"] = fields["last_observed"]
    if fields.get("last_observed_full"):
        report["last_observed_full"] = True
    if fields.get("sku"):
        report["sku"] = fields["sku"]
    return report


def _classify_browse(response: Any) -> tuple[str, dict[str, Any] | None]:
    """Map a Browse ``getItem`` response to a state + parsed body.

    A 200 is split into ``active`` (purchasable: no past ``itemEndDate`` and not
    ``OUT_OF_STOCK``/zero remaining) vs ``ended`` (a durable public record with a
    past end date or an availability signal that means it is no longer
    purchasable). That distinction is what lets the combined state name
    ``not_listed`` (seller deleted + public ended) instead of a confusing 200.
    """
    if not isinstance(response, httpx2.Response):
        # Already-parsed model/dict: treat as active unless it carries an end signal.
        body = response if isinstance(response, dict) else None
        return ("ended" if _is_ended(body) else "active"), body
    status = response.status_code
    if status == 200:
        content_type = response.headers.get("content-type", "")
        body: dict[str, Any] | None = None
        if "json" in content_type and response.content:
            import orjson

            body = orjson.loads(response.content)
        return ("ended" if _is_ended(body) else "active"), body
    if status == 404:
        return "not_found", None
    # 403 (anti-automation throttle), 410, 5xx, etc.: never read as "absent".
    return "blocked", None


def _is_ended(item: dict[str, Any] | None) -> bool:
    """True if a Browse item is no longer purchasable.

    eBay keeps a withdrawn/deleted item publicly queryable with an ``itemEndDate``
    in the past and/or ``estimatedAvailability`` signalling ``OUT_OF_STOCK`` /
    zero remaining. Either signal means the public record is ended/retained, not
    active — the "not listed anymore" state.
    """
    if not isinstance(item, dict):
        return False
    end = item.get("itemEndDate")
    if isinstance(end, str):
        try:
            # eBay timestamps are UTC ISO-8601 with a trailing Z.
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end_dt <= datetime.now(UTC):
                return True
        except ValueError:
            pass  # an unparseable end date is not treated as an end signal
    avail = item.get("estimatedAvailability")
    if isinstance(avail, dict):
        status = avail.get("estimatedAvailabilityStatus")
        if isinstance(status, str) and status.upper() in {"OUT_OF_STOCK", "UNAVAILABLE"}:
            return True
        remaining = avail.get("estimatedRemainingQuantity")
        if _as_int(remaining) == 0:
            return True
    return False


def _seller_state(inv_method: Any, sku: str | None) -> str:
    """Classify the seller-side inventory state for a SKU (present/deleted)."""
    try:
        response = inv_method(sku, raw_response=True)
    except Exception:  # noqa: BLE001 - a seller read failure must not fake a state
        return "not_checked"
    if isinstance(response, httpx2.Response):
        if response.status_code == 200:
            return "present"
        if response.status_code == 404:
            return "deleted"
        return "not_checked"
    return "present" if response is not None else "deleted"


def _combine_frontend_state(api_state: str, browse_state: str) -> str:
    """The honest, actionable combined state.

    The key insight an agent needs: a successful seller delete can leave the
    public/Browse item present for a long time. We name the durable post-delete
    public record ``not_listed`` (public ended/unpurchasable + seller gone) and
    keep ``stale_after_delete`` only for the transient window where the public
    representation still appears active (no end signal) while the seller record
    is already gone. A visible-but-ended public record with the seller still
    present is ``public_ended`` (e.g. a manually ended listing whose inventory
    was not deleted).
    """
    if browse_state == "blocked":
        return "blocked"
    if browse_state == "not_found":
        if api_state == "present":
            return "not_yet_visible"  # just published, public state propagating
        return "not_found"  # absent publicly and (deleted or unchecked)
    if browse_state == "active":
        if api_state == "deleted":
            return "stale_after_delete"  # public still active-looking, seller gone
        return "visible"  # public active and seller present/unchecked
    # browse_state == "ended"
    if api_state == "deleted":
        return "not_listed"  # seller gone AND public ended/unpurchasable
    return "public_ended"  # public ended, seller still present/unchecked


def _public_listing_state(browse_state: str, api_state: str) -> str:
    """The public-side classification on its own.

    ``retained`` is the durable ended record eBay keeps after a withdraw/delete
    when the seller record is also gone (history); ``ended`` is an ended public
    record whose seller side is still present/unchecked. Surfaced separately from
    the combined ``frontend_state`` so an agent can read the public side directly.
    """
    if browse_state == "active":
        return "active"
    if browse_state == "ended":
        return "retained" if api_state == "deleted" else "ended"
    if browse_state == "not_found":
        return "not_found"
    return "blocked"


def _expectation_met(frontend_state: str, browse_state: str, expect_browse: str) -> bool:
    """Whether the observed state satisfies the requested expectation.

    * ``active``    — the public item exists and is purchasable (browse active).
    * ``visible``   — any public representation exists, including retained
      history (browse active OR ended).
    * ``not_listed`` — seller deleted AND public ended/unpurchasable, or a 404;
      the cleanup-acceptable state. ``stale_after_delete`` (public still
      active-looking) does NOT satisfy it.
    * ``not_found`` — Browse returned 404.
    """
    if expect_browse == "active":
        return browse_state == "active"
    if expect_browse == "visible":
        return browse_state in {"active", "ended"}
    if expect_browse == "not_listed":
        return frontend_state in {"not_listed", "not_found"}
    # not_found
    return frontend_state == "not_found"


def _assert_browse_fields(
    observed: dict[str, Any] | None,
    *,
    expect_title: str | None,
    expect_description_contains: str | None,
    expect_image_count: int | None,
    expect_price: str | None,
    expect_currency: str | None,
    expect_category_id: str | None,
    expect_buying_option: str | None,
) -> list[dict[str, Any]]:
    """Field-level assertions against the Browse item.

    A 200 alone is insufficient: eBay can return a stale or different listing
    representation. Each assertion records the field, expected and observed
    values, and a match flag so the agent sees exactly which content checks
    failed. Description is matched by substring (the marker convention) so the
    full legal blob is never echoed into the report.
    """
    results: list[dict[str, Any]] = []
    item = observed if isinstance(observed, dict) else {}

    def add(field: str, expected: Any, observed_value: Any, *, match: bool) -> None:
        results.append(
            {"field": field, "expected": expected, "observed": observed_value, "match": match}
        )

    if expect_title is not None:
        title = item.get("title")
        add("title", expect_title, title, match=title == expect_title)
    if expect_description_contains is not None:
        description = item.get("description") or ""
        match = expect_description_contains in description
        add(
            "description_contains",
            expect_description_contains,
            _marker_observed(description, expect_description_contains, match),
            match=match,
        )
    if expect_image_count is not None:
        count = _browse_image_count(item)
        add("image_count", expect_image_count, count, match=count == expect_image_count)
    if expect_price is not None or expect_currency is not None:
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        if expect_price is not None:
            value = price.get("value")
            add("price.value", expect_price, value, match=str(value) == str(expect_price))
        if expect_currency is not None:
            currency = price.get("currency")
            add(
                "price.currency",
                expect_currency,
                currency,
                match=str(currency) == str(expect_currency),
            )
    if expect_category_id is not None:
        category_id = item.get("categoryId")
        add(
            "categoryId",
            expect_category_id,
            category_id,
            match=str(category_id) == str(expect_category_id),
        )
    if expect_buying_option is not None:
        options = item.get("buyingOptions") or []
        options_list = list(options) if isinstance(options, list) else []
        add(
            "buyingOptions",
            expect_buying_option,
            options_list,
            match=expect_buying_option in options_list,
        )
    return results


def _marker_observed(description: str, marker: str, match: bool) -> str:
    """Never echo the full description; report only marker presence/length."""
    if match:
        return f"<contains marker {marker!r}>"
    return f"<marker absent; description length {len(description)}>"


def _browse_image_count(item: dict[str, Any]) -> int:
    """Primary image + additional images (the 4-image gallery test counts both)."""
    count = 1 if item.get("image") else 0
    additional = item.get("additionalImages")
    if isinstance(additional, list):
        count += len(additional)
    return count


def _summarize_browse(observed: dict[str, Any] | None) -> dict[str, Any] | None:
    """Bounded allowlist summary of the last Browse item.

    Keeps the fields an assertion or a human needs (title, price, image count,
    buying options, item URL) and deliberately drops the large legal blob
    (returnTerms, seller contact, responsiblePersons, productSafetyLabels,
    sellerCustomPolicies) and the full description. Image URLs are summarized as
    a count, not echoed, to keep the report token-bounded.
    """
    if not isinstance(observed, dict):
        return None
    summary: dict[str, Any] = {}
    for field in _BROWSE_SUMMARY_FIELDS:
        if field in observed:
            summary[field] = observed[field]
    price = observed.get("price")
    if isinstance(price, dict):
        summary["price"] = {k: price.get(k) for k in ("value", "currency") if k in price}
    summary["image_count"] = _browse_image_count(observed)
    description = observed.get("description")
    if isinstance(description, str):
        summary["description_length"] = len(description)
    # Surface the end/availability signals so an agent can confirm *why* a
    # record classified as ended/retained is no longer purchasable, without
    # echoing the full legal blob.
    avail = observed.get("estimatedAvailability")
    if isinstance(avail, dict):
        summary["estimated_availability"] = {
            k: avail.get(k)
            for k in ("estimatedAvailabilityStatus", "estimatedRemainingQuantity")
            if k in avail
        }
    summary["ended"] = _is_ended(observed)
    return summary




# ---------------------------------------------------------------------------
# Actionable publish-error translation
# ---------------------------------------------------------------------------

# eBay error codes that the publish/offer path surfaces opaquely. 25002 is
# handled dynamically (it carries the missing-aspect names in its parameters);
# the rest map to a curated, actionable hint.
_TAXONOMY_LOOKUP_HINT = (
    "Look up the required aspects with `bidkit commerce taxonomy "
    "get-item-aspects-for-category CATEGORY-TREE-ID --category-id "
    "CATEGORY-ID` and add them to the inventory item's product.aspects before "
    "publishing."
)

_PUBLISH_ERROR_HINTS: dict[int, str] = {
    25007: (
        "A listing policy is missing or invalid for the marketplace. Set the "
        "offer listingPolicies (fulfillmentPolicyId, paymentPolicyId, "
        "returnPolicyId) for the listing's marketplace; these are required to "
        "publish and do not fall back to account defaults safely."
    ),
    25718: (
        "The inventory item title exceeds the marketplace limit. Shorten the "
        "title (EBAY_DE/AU/US = 80 characters) before re-publishing."
    ),
}


def enrich_publish_error(status: int, payload: Any) -> str | None:
    """Return an actionable hint for a known publish/offer error code, else None.

    ``payload`` is the eBay error envelope (a list/dict with ``errors[].errorId``).
    For 25002 the hint carries the actual missing-aspect names eBay names in
    ``errors[].parameters[].value``, instead of a generic
    "an aspect is missing" message.
    """
    code = _first_error_id(payload)
    if code is None:
        return None
    if code == 25002:
        return _missing_aspect_hint(payload)
    return _PUBLISH_ERROR_HINTS.get(code)


def _missing_aspect_hint(payload: Any) -> str:
    """Build the 25002 hint, naming the specific missing aspects when known."""
    aspects = _missing_aspects(payload)
    if aspects:
        head = (
            f"Missing required product aspects: {', '.join(aspects)}. "
            "Add them to the inventory item's product.aspects. "
        )
    else:
        head = "A category-required product aspect is missing. "
    return head + _TAXONOMY_LOOKUP_HINT


def _missing_aspects(payload: Any) -> list[str]:
    """Extract the missing-aspect names eBay returns in error parameters.

    eBay's 25002 publishes the offending aspect(s) in ``errors[].parameters``;
    each parameter is ``{"name": ..., "value": "Produktart"}`` where ``value``
    is the aspect name. Distinct, non-empty values are returned in declared
    order. Parameter name has been observed as ``aspectName``/``Aspect``/an
    index, so the value is the reliable carrier.
    """
    names: list[str] = []
    for entry in _iter_errors(payload):
        params = entry.get("parameters") if isinstance(entry, dict) else None
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, dict):
                continue
            value = param.get("value")
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned and cleaned not in names:
                    names.append(cleaned)
    return names


def _iter_errors(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        return errors if isinstance(errors, list) else []
    if isinstance(payload, list):
        return payload
    return []


def _first_error_id(payload: Any) -> int | None:
    errors: list[Any] = []
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
    elif isinstance(payload, list):
        errors = payload
    for entry in errors:
        if isinstance(entry, dict) and "errorId" in entry:
            try:
                return int(entry["errorId"])
            except (TypeError, ValueError):
                continue
    return None
