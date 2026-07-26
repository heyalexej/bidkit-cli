# Compliance API

- **Service key:** `sell_compliance`
- **CLI:** `bidkit sell compliance`
- **Version:** 1.4.1
- **Base path:** `/sell/compliance/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_compliance_v1_oas3.json`
- **Operations:** 3

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_compliance.OPERATION_ID
bidkit api schema sell_compliance.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_compliance.getListingViolations` | GET | `/listing_violation` | read | This call returns specific listing violations for the supported listing compliance types.  |
| `sell_compliance.getListingViolationsSummary` | GET | `/listing_violation_summary` | read | This call returns listing violation counts for a seller. A user can pass in one or more co |
| `sell_compliance.suppressViolation` | POST | `/suppress_listing_violation` | unknown | This call suppresses a listing violation for a specific listing. Only listing violations i |

Command path prefix: `bidkit sell compliance <operation>`.

## Examples

```bash
# sell_compliance.getListingViolations
bidkit sell compliance get-listing-violations --limit 30 --format json
# sell_compliance.getListingViolationsSummary
bidkit sell compliance get-listing-violations-summary --format json
# sell_compliance.suppressViolation
bidkit sell compliance suppress-violation --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
