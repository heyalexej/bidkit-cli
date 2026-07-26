# Key Management API

- **Service key:** `developer_key_management`
- **CLI:** `bidkit developer key-management`
- **Version:** v1.0.0
- **Base path:** `/developer/key_management/v1`  ·  **Subdomain:** `apiz`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `developer_key_management_v1_oas3.json`
- **Operations:** 3

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe developer_key_management.OPERATION_ID
bidkit api schema developer_key_management.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `developer_key_management.createSigningKey` | POST | `/signing_key` | unknown | Creates keypairs using the selected cipher. |
| `developer_key_management.getSigningKey` | GET | `/signing_key/{signing_key_id}` | read | Retrieves a specific keypair and metadata for a specified signing key ID associated with t |
| `developer_key_management.getSigningKeys` | GET | `/signing_key` | read | Retrieves keypairs and metadata for all keypairs associated with the application key makin |

Command path prefix: `bidkit developer key-management <operation>`.

## Examples

```bash
# developer_key_management.createSigningKey
bidkit developer key-management create-signing-key --body @request.json --format json --dry-run
# developer_key_management.getSigningKey
bidkit developer key-management get-signing-key SIGNING-KEY-ID --format json
# developer_key_management.getSigningKeys
bidkit developer key-management get-signing-keys --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
