# Translation API

- **Service key:** `commerce_translation`
- **CLI:** `bidkit commerce translation`
- **Version:** v1_beta.1.6
- **Base path:** `/commerce/translation/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_translation_v1_beta_oas3.json`
- **Operations:** 1

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_translation.OPERATION_ID
bidkit api schema commerce_translation.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_translation.translate` | POST | `/translate` | read | This method translates listing title and listing description text from one language into a |

Command path prefix: `bidkit commerce translation <operation>`.

## Examples

```bash
# commerce_translation.translate
bidkit commerce translation translate --body @request.json --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
