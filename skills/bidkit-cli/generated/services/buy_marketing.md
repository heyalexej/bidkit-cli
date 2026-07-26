# Buy Marketing API

- **Service key:** `buy_marketing`
- **CLI:** `bidkit buy marketing`
- **Version:** 1.1.0
- **Base path:** `/buy/marketing/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_marketing_v1_beta_oas3.json`
- **Operations:** 3

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_marketing.OPERATION_ID
bidkit api schema buy_marketing.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_marketing.getMerchandisedProducts` | GET | `/merchandised_product` | read | This method returns an array of products based on the category and metric specified. This  |
| `buy_marketing.getMostWatchedItems` | GET | `/most_watched_items` | read | This method retrieves items with the highest watch counts in a specific category. The leaf |
| `buy_marketing.getSimilarItems` | GET | `/similar_items` | read | This method retrieves items that are similar to the specified item. Items are considered s |

Command path prefix: `bidkit buy marketing <operation>`.

## Examples

```bash
# buy_marketing.getMerchandisedProducts
bidkit buy marketing get-merchandised-products --category-id VALUE --metric-name VALUE --limit 30 --format json
# buy_marketing.getMostWatchedItems
bidkit buy marketing get-most-watched-items --category-id VALUE --format json
# buy_marketing.getSimilarItems
bidkit buy marketing get-similar-items --item-id VALUE --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
