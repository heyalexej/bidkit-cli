# Post Order Case Management API

- **Service key:** `case`
- **CLI:** `bidkit post-order case`
- **Version:** 0.1
- **Base path:** `/post-order/v2`  ·  **Subdomain:** `api`
- **Auth scheme:** `TOKEN`  ·  **Requires signature:** False
- **Source spec:** `case_oas3.json`
- **Operations:** 7

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe case.OPERATION_ID
bidkit api schema case.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `case.appealCaseDecision` | POST | `/casemanagement/{caseId}/appeal` | unknown | Buyer or seller appeals a case decision |
| `case.closeCase` | POST | `/casemanagement/{caseId}/close` | unknown | Buyer closes a case |
| `case.getCase` | GET | `/casemanagement/{caseId}` | read | Retrieve the details related to a specific case |
| `case.issueCaseRefund` | POST | `/casemanagement/{caseId}/issue_refund` | unknown | Seller issues a refund for a case |
| `case.provideReturnShipmentInfo` | POST | `/casemanagement/{caseId}/provide_shipment_info` | unknown | Buyer provides return shipment information |
| `case.providesReturnAddress` | POST | `/casemanagement/{caseId}/provide_return_address` | unknown | Seller provides a return address to the buyer |
| `case.search` | GET | `/casemanagement/search` | read | This call is used to search for cases using multiple filter types. |

Command path prefix: `bidkit post-order case <operation>`.

## Examples

```bash
# case.appealCaseDecision
bidkit post-order case appeal-case-decision CASE-ID --format json --dry-run
# case.closeCase
bidkit post-order case close-case CASE-ID --format json --dry-run
# case.getCase
bidkit post-order case get-case CASE-ID --format json
# case.issueCaseRefund
bidkit post-order case issue-case-refund CASE-ID --format json --dry-run
# case.provideReturnShipmentInfo
bidkit post-order case provide-return-shipment-info CASE-ID --format json --dry-run
# case.providesReturnAddress
bidkit post-order case provides-return-address CASE-ID --format json --dry-run
# case.search
bidkit post-order case search --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
