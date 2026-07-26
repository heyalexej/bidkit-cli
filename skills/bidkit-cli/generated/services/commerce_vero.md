# Vero Public API's

- **Service key:** `commerce_vero`
- **CLI:** `bidkit commerce vero`
- **Version:** 1.0.0
- **Base path:** `/commerce/vero/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_vero_v1_oas3.json`
- **Operations:** 5

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_vero.OPERATION_ID
bidkit api schema commerce_vero.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_vero.createVeroReport` | POST | `/vero_report` | unknown | Important! You must be a member of the Verified Rights Owner (VeRO) Program to use this ca |
| `commerce_vero.getVeroReasonCode` | GET | `/vero_reason_code/{vero_reason_code_id}` | read | Important! You must be a member of the Verified Rights Owner (VeRO) Program to use this ca |
| `commerce_vero.getVeroReasonCodes` | GET | `/vero_reason_code` | read | Important! You must be a member of the Verified Rights Owner (VeRO) Program to use this ca |
| `commerce_vero.getVeroReport` | GET | `/vero_report/{vero_report_id}` | read | Important! You must be a member of the Verified Rights Owner (VeRO) Program to use this ca |
| `commerce_vero.getVeroReportItems` | GET | `/vero_report_items` | read | Retrieves status for VERO infringement reports by Brand. |

Command path prefix: `bidkit commerce vero <operation>`.

## Examples

```bash
# commerce_vero.createVeroReport
bidkit commerce vero create-vero-report --body @request.json --format json --dry-run
# commerce_vero.getVeroReasonCode
bidkit commerce vero get-vero-reason-code VERO-REASON-CODE-ID --format json
# commerce_vero.getVeroReasonCodes
bidkit commerce vero get-vero-reason-codes --format json
# commerce_vero.getVeroReport
bidkit commerce vero get-vero-report VERO-REPORT-ID --format json
# commerce_vero.getVeroReportItems
bidkit commerce vero get-vero-report-items --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
