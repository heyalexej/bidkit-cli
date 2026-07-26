# Workflow: publish an inventory item

Intent: create/replace an inventory item, then publish an offer. Every step names its
canonical operation key so you can fall back to `bidkit api describe <key>` or `api call <key>`.

## 1. Inspect the model (offline)

```bash
bidkit api schema sell_inventory.createOrReplaceInventoryItem request
bidkit api schema sell_inventory.createOffer request
```

## 2. Dry-run the create (no network, no token)

```bash
bidkit sell inventory create-or-replace-inventory-item TEST-SKU \
  --body @item.json --dry-run
```

Confirm the resolved URL, body shape, and `risk: write`. For a German listing
add `--marketplace EBAY_DE --marketplace-locale`; the preview's
`config_injected_headers` then shows the `Content-Language: de-DE` /
`Accept-Language: de-DE` the SDK will send on the wire (these are *not* under
`headers`, which only holds the explicit `--header` values you passed).

## 3. Create the inventory item

```bash
bidkit sell inventory create-or-replace-inventory-item TEST-SKU \
  --body @item.json --allow-write --format json
```

## 4. Create an offer for it

```bash
bidkit sell inventory create-offer --body @offer.json --allow-write --format json
```

## 5. Verify

```bash
bidkit sell inventory get-inventory-item TEST-SKU
bidkit sell inventory get-offers --sku TEST-SKU
```

After a write you can also pass `--verify-live --wait-for-live 30` to poll the
API readback and confirm the request was accepted. The report compares the
request as a recursive *subset* of the readback, so normal eBay enrichment
(`availability.allocationByFormat`, server timestamps) does **not** cause a
false failure; it reports `api_verified` (the readback) separately from
`frontend_verified` (always `null` — the public listing page is intentionally
not polled and may lag the API by minutes / be throttled). Nested server-added
fields are now reported as dotted paths
(`availability.shipToLocationAvailability.allocationByFormat`).

## Verifying the PUBLIC listing page

`--verify-live` checks the seller API only. To prove what the *public*/Browse
representation shows (including `stale_after_delete` after a delete), use the
public verifier — see `references/workflows/verify-public.md`:

```bash
bidkit sell inventory verify-public --listing-id LISTING-ID --sku SKU \
  --expect not_found --wait 120
```

## Controlled test runs (test mode + run ledger)

For throwaway test listings, gate the write with `--test-mode` so a description
marker is required, scrambled provenance needs explicit consent, and a run id is
carried for traceability:

```bash
bidkit sell inventory create-or-replace-inventory-item TEST-SKU \
  --body @item.json --test-mode --allow-write
```

Record every test artifact in a durable ledger and produce a cleanup report
that distinguishes seller-records-deleted, frontend-converged, and
financially-reversible (always false — deleting a record cannot reverse a fee
eBay has already booked):

```bash
bidkit sell inventory test-run init --source-sku RADIO1
bidkit sell inventory test-run record --run-id RUN --sku TEST-SKU --listing-id L
bidkit sell inventory test-run cleanup-report --run-id RUN
```

## Updating an existing offer (replace-like PUT)

`updateOffer` and `createOrReplaceInventoryItem` treat the body as a *full
replacement*: an omitted field reverts to the account/API default. To change
only some fields, use `--merge` to GET the current state, apply your patch, and
PUT the merged body:

```bash
bidkit sell inventory update-offer OFFER-ID \
  --body @offer-patch.json --merge --allow-write --format json
```

## Publish failures

`publishOffer` returns `25002` when a category-required product aspect is
missing. The error hint names the specific missing aspects (e.g.
`Produktart`, `Marke`, parsed from the API parameters) and points at the
taxonomy lookup:

```bash
bidkit commerce taxonomy get-item-aspects-for-category CATEGORY-TREE-ID \
  --category-id CATEGORY-ID
```

## Underlying operation keys

- `sell_inventory.createOrReplaceInventoryItem`
- `sell_inventory.createOffer`
- `sell_inventory.publishOffer` (use `--allow-write --yes` if it deletes prior state)
- `sell_inventory.getInventoryItem`, `sell_inventory.getOffers`

Never hide the keys: log them and the returned `x-ebay-c-request-id`.
