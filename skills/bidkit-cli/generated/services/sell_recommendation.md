# Recommendation API

- **Service key:** `sell_recommendation`
- **CLI:** `bidkit sell recommendation`
- **Version:** v1.1.0
- **Base path:** `/sell/recommendation/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_recommendation_v1_oas3.json`
- **Operations:** 1

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_recommendation.OPERATION_ID
bidkit api schema sell_recommendation.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_recommendation.findListingRecommendations` | POST | `/find` | read | The find method currently returns information for a single recommendation type ( AD ) whic |

Command path prefix: `bidkit sell recommendation <operation>`.

## Examples

```bash
# sell_recommendation.findListingRecommendations
bidkit sell recommendation find-listing-recommendations --body @request.json --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
