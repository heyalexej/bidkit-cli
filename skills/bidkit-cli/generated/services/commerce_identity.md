# Identity API

- **Service key:** `commerce_identity`
- **CLI:** `bidkit commerce identity`
- **Version:** v2.0.0
- **Base path:** `/commerce/identity/v1`  ·  **Subdomain:** `apiz`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_identity_v1_oas3.json`
- **Operations:** 1

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_identity.OPERATION_ID
bidkit api schema commerce_identity.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_identity.getUser` | GET | `/user/` | read | This method retrieves the account profile information for an authenticated user, which req |

Command path prefix: `bidkit commerce identity <operation>`.

## Examples

```bash
# commerce_identity.getUser
bidkit commerce identity get-user --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
