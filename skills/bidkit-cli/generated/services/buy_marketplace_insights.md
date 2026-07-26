# Buy Marketing API

- **Service key:** `buy_marketplace_insights`
- **CLI:** `bidkit buy marketplace-insights`
- **Version:** v1_beta.2.0
- **Base path:** `/buy/marketing/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_marketplace_insights_v1_beta_oas3.json`
- **Operations:** 1

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_marketplace_insights.OPERATION_ID
bidkit api schema buy_marketplace_insights.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_marketplace_insights.getMerchandisedProducts` | GET | `/merchandised_product` | read | This method returns an array of products based on the category and metric specified. This  |

Command path prefix: `bidkit buy marketplace-insights <operation>`.

## Examples

```bash
# buy_marketplace_insights.getMerchandisedProducts
bidkit buy marketplace-insights get-merchandised-products --category-id VALUE --metric-name VALUE --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
