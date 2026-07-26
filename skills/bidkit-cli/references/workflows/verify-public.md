# Workflow: verify the public/Browse state of a listing

Intent: after a create/publish or a withdraw/delete, prove what the *public*
(Browse API) representation actually shows, including the honest case where the
seller side is gone but the public side is still catching up. `--verify-live`
only checks the seller-side API readback; this workflow checks the public side.

## Verify a listing is publicly visible (after publish)

```bash
bidkit sell inventory verify-public --listing-id 358844010590 \
  --expect visible \
  --expect-title "Vintage Radio" \
  --expect-description-contains "TEST ONLY" \
  --expect-image-count 4 \
  --expect-price 12.50 --expect-currency EUR \
  --wait 300 --poll 15
```

Browse API (`buy_browse.getItem`) is the primary machine check. A 200 alone is
insufficient, so field-level assertions compare title, the test marker, image
count, price/currency, category, and buying option and report each mismatch.
HTTP 403 (eBay's anti-automation throttle) is **never** treated as proof the
item is absent — it is surfaced as `blocked`.

## Verify a listing is gone after a delete

```bash
bidkit sell inventory verify-public --listing-id 358844010590 \
  --sku AAAAA --expect not_found --wait 120
```

Pass `--sku` to read the seller-side state too. The report can then say
`stale_after_delete` (seller deleted, public still catching up) instead of
leaving the result ambiguous.

## States (act on these, never on prose)

`not_checked`, `not_yet_visible`, `visible`, `updated`, `seller_active`,
`public_active`, `public_ended`, `stale_after_delete`, `not_listed`,
`not_found`, `blocked`, `timeout`.

`not_listed` is the durable post-delete cleanup state: **seller deleted AND public
ended/unpurchasable**. `public_ended` is an ended public record whose seller
side is still present; `stale_after_delete` is the transient window where the
public side still looks active while the seller record is already gone.

**Cleanup is converged when `frontend_state` is `not_found`, `not_listed`,
`public_ended`, or `stale_after_delete`** (the latter two with `api_state:
deleted`). A `blocked` result means "do not conclude"; retry later. Pass `--sku`
(or let `test-run cleanup-report` recover it from the ledger) so the seller
side is read — otherwise the combined state cannot reach `not_listed`.

## Report shape

```json
{
  "listing_id": "358844010590",
  "api_state": "deleted",
  "browse_state": "visible",
  "frontend_state": "stale_after_delete",
  "attempts": 12,
  "elapsed_seconds": 180,
  "last_http_status": 200,
  "retry_safe": true,
  "expected": "not_found",
  "met_expectation": false,
  "content_verified": true,
  "assertions": [ {"field": "title", "match": true, "...": "..."} ],
  "last_observed": {"title": "...", "image_count": 4, "...": "..."}
}
```

`retry_safe` is always true: verification is read-only and idempotent. The
`last_observed` summary is a bounded allowlist — the large legal-information /
seller-contact blob from the Browse response is never echoed.

## Underlying operation key

- `buy_browse.getItem` (primary check)
- `sell_inventory.getInventoryItem` (seller-side state, only when `--sku` is given)
