# Post Order Inquiry API

- **Service key:** `inquiry`
- **CLI:** `bidkit post-order inquiry`
- **Version:** 0.1
- **Base path:** `/post-order/v2`  ·  **Subdomain:** `api`
- **Auth scheme:** `TOKEN`  ·  **Requires signature:** False
- **Source spec:** `inquiry_oas3.json`
- **Operations:** 11

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe inquiry.OPERATION_ID
bidkit api schema inquiry.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `inquiry.checkInquiryEligibility` | POST | `/inquiry/check_eligibility` | unknown | Check if a buyer is eligible to open an inquiry on an order |
| `inquiry.closeInquiry` | POST | `/inquiry/{inquiryId}/close` | unknown | Close an inquiry for the buyer |
| `inquiry.confirmInquiryRefund` | POST | `/inquiry/{inquiryId}/confirm_refund` | unknown | Buyer confirms the refund from an inquiry was received |
| `inquiry.createInquiry` | POST | `/inquiry` | unknown | Buyer confirms the refund from an inquiry was received |
| `inquiry.escalateInquiry` | POST | `/inquiry/{inquiryId}/escalate` | unknown | Escalate an inquiry to an INR case |
| `inquiry.getInquiry` | GET | `/inquiry/{inquiryId}` | read | Retrieve the history and details related to a specific inquiry |
| `inquiry.issueInquiryRefund` | POST | `/inquiry/{inquiryId}/issue_refund` | unknown | Issue a refund for an inquiry |
| `inquiry.provideInquiryRefundInfo` | POST | `/inquiry/{inquiryId}/provide_refund_info` | unknown | Provide refund information about an inquiry to the buyer |
| `inquiry.provideInquiryShipmentInfo` | POST | `/inquiry/{inquiryId}/provide_shipment_info` | unknown | Provide shipment information for an inquiry |
| `inquiry.search` | GET | `/inquiry/search` | read | This call is used to search for inquiries using multiple filter types. |
| `inquiry.sendInquiryMessage` | POST | `/inquiry/{inquiryId}/send_message` | unknown | Contact the buyer or seller about an inquiry |

Command path prefix: `bidkit post-order inquiry <operation>`.

## Examples

```bash
# inquiry.checkInquiryEligibility
bidkit post-order inquiry check-inquiry-eligibility --format json --dry-run
# inquiry.closeInquiry
bidkit post-order inquiry close-inquiry INQUIRY-ID --format json --dry-run
# inquiry.confirmInquiryRefund
bidkit post-order inquiry confirm-inquiry-refund INQUIRY-ID --format json --dry-run
# inquiry.createInquiry
bidkit post-order inquiry create-inquiry --format json --dry-run
# inquiry.escalateInquiry
bidkit post-order inquiry escalate-inquiry INQUIRY-ID --format json --dry-run
# inquiry.getInquiry
bidkit post-order inquiry get-inquiry INQUIRY-ID --format json
# inquiry.issueInquiryRefund
bidkit post-order inquiry issue-inquiry-refund INQUIRY-ID --format json --dry-run
# inquiry.provideInquiryRefundInfo
bidkit post-order inquiry provide-inquiry-refund-info INQUIRY-ID --format json --dry-run
# inquiry.provideInquiryShipmentInfo
bidkit post-order inquiry provide-inquiry-shipment-info INQUIRY-ID --format json --dry-run
# inquiry.search
bidkit post-order inquiry search --limit 30 --format json
# inquiry.sendInquiryMessage
bidkit post-order inquiry send-inquiry-message INQUIRY-ID --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
