# Catalog API

- **Service key:** `commerce_catalog`
- **CLI:** `bidkit commerce catalog`
- **Version:** v1_beta.5.3
- **Base path:** `/commerce/catalog/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_catalog_v1_beta_oas3.json`
- **Operations:** 2

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_catalog.OPERATION_ID
bidkit api schema commerce_catalog.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_catalog.getProduct` | GET | `/product/{epid}` | read | This method retrieves details of the catalog product identified by the eBay product identi |
| `commerce_catalog.search` | GET | `/product_summary/search` | read | This method searches for and retrieves summaries of one or more products in the eBay catal |

Command path prefix: `bidkit commerce catalog <operation>`.

## Examples

```bash
# commerce_catalog.getProduct
bidkit commerce catalog get-product EPID --format json
# commerce_catalog.search
bidkit commerce catalog search --q VALUE --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
