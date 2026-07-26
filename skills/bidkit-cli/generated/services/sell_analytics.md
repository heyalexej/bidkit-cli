# Analytics API

- **Service key:** `sell_analytics`
- **CLI:** `bidkit sell analytics`
- **Version:** 1.3.2
- **Base path:** `/sell/analytics/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_analytics_v1_oas3.json`
- **Operations:** 4

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_analytics.OPERATION_ID
bidkit api schema sell_analytics.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_analytics.findSellerStandardsProfiles` | GET | `/seller_standards_profile` | read | This call retrieves all the standards profiles for the associated seller. A standards prof |
| `sell_analytics.getCustomerServiceMetric` | GET | `/customer_service_metric/{customer_service_metric_type}/{evaluation_type}` | read | Use this method to retrieve a seller's performance and rating for the customer service met |
| `sell_analytics.getSellerStandardsProfile` | GET | `/seller_standards_profile/{program}/{cycle}` | read | This call retrieves a single standards profile for the associated seller. A standards prof |
| `sell_analytics.getTrafficReport` | GET | `/traffic_report` | read | This method returns a report that details the user traffic received by a seller's listings |

Command path prefix: `bidkit sell analytics <operation>`.

## Examples

```bash
# sell_analytics.findSellerStandardsProfiles
bidkit sell analytics find-seller-standards-profiles --format json
# sell_analytics.getCustomerServiceMetric
bidkit sell analytics get-customer-service-metric CUSTOMER-SERVICE-METRIC-TYPE EVALUATION-TYPE --evaluation-marketplace-id VALUE --format json
# sell_analytics.getSellerStandardsProfile
bidkit sell analytics get-seller-standards-profile CYCLE PROGRAM --format json
# sell_analytics.getTrafficReport
bidkit sell analytics get-traffic-report --dimension VALUE --filter VALUE --metric VALUE --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
