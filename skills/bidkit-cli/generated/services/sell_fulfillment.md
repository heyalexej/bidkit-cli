# Fulfillment API

- **Service key:** `sell_fulfillment`
- **CLI:** `bidkit sell fulfillment`
- **Version:** v1.20.6
- **Base path:** `/sell/fulfillment/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_fulfillment_v1_oas3.json`
- **Operations:** 15

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_fulfillment.OPERATION_ID
bidkit api schema sell_fulfillment.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_fulfillment.acceptPaymentDispute` | POST | `/payment_dispute/{payment_dispute_id}/accept` | unknown | Accept Payment Dispute |
| `sell_fulfillment.addEvidence` | POST | `/payment_dispute/{payment_dispute_id}/add_evidence` | unknown | Add an Evidence File |
| `sell_fulfillment.contestPaymentDispute` | POST | `/payment_dispute/{payment_dispute_id}/contest` | unknown | Contest Payment Dispute |
| `sell_fulfillment.createShippingFulfillment` | POST | `/order/{orderId}/shipping_fulfillment` | unknown | When you group an order's line items into one or more packages, each package requires a co |
| `sell_fulfillment.fetchEvidenceContent` | GET | `/payment_dispute/{payment_dispute_id}/fetch_evidence_content` | read | Get Payment Dispute Evidence File |
| `sell_fulfillment.getActivities` | GET | `/payment_dispute/{payment_dispute_id}/activity` | read | Get Payment Dispute Activity |
| `sell_fulfillment.getOrder` | GET | `/order/{orderId}` | read | Use this call to retrieve the contents of an order based on its unique identifier, orderId |
| `sell_fulfillment.getOrders` | GET | `/order` | read | Use this method to search for and retrieve one or more orders based on their creation date |
| `sell_fulfillment.getPaymentDispute` | GET | `/payment_dispute/{payment_dispute_id}` | read | Get Payment Dispute Details |
| `sell_fulfillment.getPaymentDisputeSummaries` | GET | `/payment_dispute_summary` | read | Search Payment Dispute by Filters |
| `sell_fulfillment.getShippingFulfillment` | GET | `/order/{orderId}/shipping_fulfillment/{fulfillmentId}` | read | Use this call to retrieve the contents of a fulfillment based on its unique identifier, fu |
| `sell_fulfillment.getShippingFulfillments` | GET | `/order/{orderId}/shipping_fulfillment` | read | Use this call to retrieve the contents of all fulfillments currently defined for a specifi |
| `sell_fulfillment.issueRefund` | POST | `/order/{order_id}/issue_refund` | unknown | Issue Refund |
| `sell_fulfillment.updateEvidence` | POST | `/payment_dispute/{payment_dispute_id}/update_evidence` | unknown | Update evidence |
| `sell_fulfillment.uploadEvidenceFile` | POST | `/payment_dispute/{payment_dispute_id}/upload_evidence_file` | unknown | Upload an Evidence File |

Command path prefix: `bidkit sell fulfillment <operation>`.

## Examples

```bash
# sell_fulfillment.acceptPaymentDispute
bidkit sell fulfillment accept-payment-dispute PAYMENT-DISPUTE-ID --body @request.json --format json --dry-run
# sell_fulfillment.addEvidence
bidkit sell fulfillment add-evidence PAYMENT-DISPUTE-ID --body @request.json --format json --dry-run
# sell_fulfillment.contestPaymentDispute
bidkit sell fulfillment contest-payment-dispute PAYMENT-DISPUTE-ID --body @request.json --format json --dry-run
# sell_fulfillment.createShippingFulfillment
bidkit sell fulfillment create-shipping-fulfillment ORDER-ID --body @request.json --format json --dry-run
# sell_fulfillment.fetchEvidenceContent
bidkit sell fulfillment fetch-evidence-content PAYMENT-DISPUTE-ID --evidence-id VALUE --file-id VALUE --format json
# sell_fulfillment.getActivities
bidkit sell fulfillment get-activities PAYMENT-DISPUTE-ID --format json
# sell_fulfillment.getOrder
bidkit sell fulfillment get-order ORDER-ID --format json
# sell_fulfillment.getOrders
bidkit sell fulfillment get-orders --limit 30 --format json
# sell_fulfillment.getPaymentDispute
bidkit sell fulfillment get-payment-dispute PAYMENT-DISPUTE-ID --format json
# sell_fulfillment.getPaymentDisputeSummaries
bidkit sell fulfillment get-payment-dispute-summaries --limit 30 --format json
# sell_fulfillment.getShippingFulfillment
bidkit sell fulfillment get-shipping-fulfillment FULFILLMENT-ID ORDER-ID --format json
# sell_fulfillment.getShippingFulfillments
bidkit sell fulfillment get-shipping-fulfillments ORDER-ID --format json
# sell_fulfillment.issueRefund
bidkit sell fulfillment issue-refund ORDER-ID --body @request.json --format json --dry-run
# sell_fulfillment.updateEvidence
bidkit sell fulfillment update-evidence PAYMENT-DISPUTE-ID --body @request.json --format json --dry-run
# sell_fulfillment.uploadEvidenceFile
bidkit sell fulfillment upload-evidence-file PAYMENT-DISPUTE-ID --file file=@./file --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
