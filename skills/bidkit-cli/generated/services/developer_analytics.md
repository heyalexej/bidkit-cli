# Analytics API

- **Service key:** `developer_analytics`
- **CLI:** `bidkit developer analytics`
- **Version:** v1_beta.0.1
- **Base path:** `/developer/analytics/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `developer_analytics_v1_beta_oas3.json`
- **Operations:** 2

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe developer_analytics.OPERATION_ID
bidkit api schema developer_analytics.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `developer_analytics.getRateLimits` | GET | `/rate_limit/` | read | Retrieves call limit and utilization data for an application based on search criteria. |
| `developer_analytics.getUserRateLimits` | GET | `/user_rate_limit/` | read | Retrieves call limit and utilization data for a user based on search criteria. |

Command path prefix: `bidkit developer analytics <operation>`.

## Examples

```bash
# developer_analytics.getRateLimits
bidkit developer analytics get-rate-limits --format json
# developer_analytics.getUserRateLimits
bidkit developer analytics get-user-rate-limits --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
