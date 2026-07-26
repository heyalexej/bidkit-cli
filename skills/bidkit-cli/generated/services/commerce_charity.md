# Charity API

- **Service key:** `commerce_charity`
- **CLI:** `bidkit commerce charity`
- **Version:** v1.2.1
- **Base path:** `/commerce/charity/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_charity_v1_oas3.json`
- **Operations:** 2

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_charity.OPERATION_ID
bidkit api schema commerce_charity.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_charity.getCharityOrg` | GET | `/charity_org/{charity_org_id}` | read | This call is used to retrieve detailed information about supported charitable organization |
| `commerce_charity.getCharityOrgs` | GET | `/charity_org` | read | This call is used to search for supported charitable organizations. It allows users to sea |

Command path prefix: `bidkit commerce charity <operation>`.

## Examples

```bash
# commerce_charity.getCharityOrg
bidkit commerce charity get-charity-org CHARITY-ORG-ID --format json
# commerce_charity.getCharityOrgs
bidkit commerce charity get-charity-orgs --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
