# Client Registration API

- **Service key:** `developer_client_registration`
- **CLI:** `bidkit developer client-registration`
- **Version:** v1.0.0
- **Base path:** `/developer/registration/v1`  ·  **Subdomain:** `tppz`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `developer_client_registration_v1_oas3.json`
- **Operations:** 1

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe developer_client_registration.OPERATION_ID
bidkit api schema developer_client_registration.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `developer_client_registration.registerClient` | POST | `/client/register` | unknown | Registers a new third party financial application with eBay. |

Command path prefix: `bidkit developer client-registration <operation>`.

## Examples

```bash
# developer_client_registration.registerClient
bidkit developer client-registration register-client --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
