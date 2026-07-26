# Post Order Cancellation API

- **Service key:** `cancellation`
- **CLI:** `bidkit post-order cancellation`
- **Version:** 0.1
- **Base path:** `/post-order/v2`  ·  **Subdomain:** `api`
- **Auth scheme:** `TOKEN`  ·  **Requires signature:** False
- **Source spec:** `cancellation_oas3.json`
- **Operations:** 7

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe cancellation.OPERATION_ID
bidkit api schema cancellation.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `cancellation.approveCancellationRequest` | POST | `/cancellation/{cancelId}/approve` | unknown | Seller approves a cancellation request |
| `cancellation.checkCancellationEligibility` | POST | `/cancellation/check_eligibility` | unknown | Check the eligibility of an order cancellation |
| `cancellation.confirmRefundReceived` | POST | `/cancellation/{cancelId}/confirm` | unknown | Buyer confirms the refund from a cancellation was received |
| `cancellation.createCancellation` | POST | `/cancellation` | unknown | Request or perform an order cancellation |
| `cancellation.getCancellation` | GET | `/cancellation/{cancelId}` | read | Request or perform an order cancellation |
| `cancellation.rejectCancellationRequest` | POST | `/cancellation/{cancelId}/reject` | unknown | Seller rejects a cancellation request |
| `cancellation.search` | GET | `/cancellation/search` | read | Search for cancellations |

Command path prefix: `bidkit post-order cancellation <operation>`.

## Examples

```bash
# cancellation.approveCancellationRequest
bidkit post-order cancellation approve-cancellation-request CANCEL-ID --format json --dry-run
# cancellation.checkCancellationEligibility
bidkit post-order cancellation check-cancellation-eligibility --format json --dry-run
# cancellation.confirmRefundReceived
bidkit post-order cancellation confirm-refund-received CANCEL-ID --format json --dry-run
# cancellation.createCancellation
bidkit post-order cancellation create-cancellation --format json --dry-run
# cancellation.getCancellation
bidkit post-order cancellation get-cancellation CANCEL-ID --format json
# cancellation.rejectCancellationRequest
bidkit post-order cancellation reject-cancellation-request CANCEL-ID --format json --dry-run
# cancellation.search
bidkit post-order cancellation search --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
