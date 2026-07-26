# Listing API

- **Service key:** `sell_listing`
- **CLI:** `bidkit sell listing`
- **Version:** v1_beta.2.1
- **Base path:** `/sell/listing/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_listing_v1_beta_oas3.json`
- **Operations:** 1

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_listing.OPERATION_ID
bidkit api schema sell_listing.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_listing.createItemDraft` | POST | `/item_draft/` | unknown | This call gives Partners the ability to create an eBay draft of a item for their seller us |

Command path prefix: `bidkit sell listing <operation>`.

## Examples

```bash
# sell_listing.createItemDraft
bidkit sell listing create-item-draft --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
