# Post Order Return API

- **Service key:** `return`
- **CLI:** `bidkit post-order return`
- **Version:** 0.1
- **Base path:** `/post-order/v2`  ·  **Subdomain:** `api`
- **Auth scheme:** `TOKEN`  ·  **Requires signature:** False
- **Source spec:** `return_oas3.json`
- **Operations:** 33

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe return.OPERATION_ID
bidkit api schema return.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `return.addShippingLabelInfo` | POST | `/return/{returnId}/add_shipping_label` | unknown | Create or update a shipping label provided by the seller |
| `return.cancelReturnRequest` | POST | `/return/{returnId}/cancel` | unknown | Cancel a return request |
| `return.checkReturnEligibility` | POST | `/return/check_eligibility` | unknown | Check to see if an item is eligible for a return |
| `return.checkShippingLabelEligibility` | GET | `/return/{returnId}/check_label_print_eligibility` | read | Validate the eligibility of an existing shipping label |
| `return.createReturnDraft` | POST | `/return/draft` | unknown | Create a return draft |
| `return.createReturnRequest` | POST | `/return` | unknown | Request a return for an item |
| `return.createReturnShippingLabel` | POST | `/return/{returnId}/initiate_shipping_label` | unknown | Create an eBay shipping label for the buyer |
| `return.deleteReturnDraftFile` | DELETE | `/return/draft/{draftId}/file/{fileId}` | destructive | Delete a file associated with a return draft |
| `return.escalateReturn` | POST | `/return/{returnId}/escalate` | unknown | Escalate an existing return to eBay customer support |
| `return.getReturn` | GET | `/return/{returnId}` | read | Retrieve the details of a specific return |
| `return.getReturnDraft` | GET | `/return/draft/{draftId}` | read | Retrieve a return draft |
| `return.getReturnDraftFiles` | GET | `/return/draft/{draftId}/files` | read | Retrieve the files associated with a return draft |
| `return.getReturnEstimate` | POST | `/return/estimate` | unknown | Buyer-facing call to retrieve the estimated refund amount and return shipping costs associ |
| `return.getReturnFiles` | GET | `/return/{returnId}/files` | read | Retrieve the files associated with a return |
| `return.getReturnPreferences` | GET | `/return/preference` | read | Retrieve seller's return preferences |
| `return.getReturnShippingLabel` | GET | `/return/{returnId}/get_shipping_label` | read | Retrieve the data for an existing shipping label |
| `return.getShipmentTrackingInfo` | GET | `/return/{returnId}/tracking` | read | Retrieve shipment tracking activity for a return |
| `return.issueReturnRefund` | POST | `/return/{returnId}/issue_refund` | unknown | Issue a refund |
| `return.markReturnReceived` | POST | `/return/{returnId}/mark_as_received` | unknown | Mark a returned item as received |
| `return.markReturnRefundReceived` | POST | `/return/{returnId}/mark_refund_received` | unknown | Mark a refund as received |
| `return.markReturnRefundSent` | POST | `/return/{returnId}/mark_refund_sent` | unknown | Notify the buyer that a refund has been issued |
| `return.markReturnShipped` | POST | `/return/{returnId}/mark_as_shipped` | unknown | Mark a return as shipped |
| `return.processReturnRequest` | POST | `/return/{returnId}/decide` | unknown | Perform an action on a return, such as APPROVE |
| `return.search` | GET | `/return/search` | read | Retrieve details on items being returned |
| `return.sendReturnMessage` | POST | `/return/{returnId}/send_message` | unknown | Send a message to the buyer or seller regarding a return |
| `return.sendReturnShippingLabel` | POST | `/return/{returnId}/send_shipping_label` | unknown | Send a shipping label to an email address |
| `return.setReturnPreferences` | POST | `/return/preference` | unknown | Set seller's return preferences |
| `return.submitReturnFile` | POST | `/return/{returnId}/file/submit` | unknown | Activate the files associated with a return |
| `return.updateReturnDraft` | PUT | `/return/draft/{draftId}` | write | Update an existing return draft |
| `return.updateShipmentTrackingInfo` | PUT | `/return/{returnId}/update_tracking` | write | Update shipment tracking information for an item being returned. |
| `return.uploadReturnDraftFile` | POST | `/return/draft/{draftId}/file/upload` | unknown | Upload the files relating to a return draft |
| `return.uploadReturnFile` | POST | `/return/{returnId}/file/upload` | unknown | Upload the files relating to a return |
| `return.voidShippingLabel` | POST | `/return/{returnId}/void_shipping_label` | unknown | Void a shipping label |

Command path prefix: `bidkit post-order return <operation>`.

## Examples

```bash
# return.addShippingLabelInfo
bidkit post-order return add-shipping-label-info RETURN-ID --format json --dry-run
# return.cancelReturnRequest
bidkit post-order return cancel-return-request RETURN-ID --format json --dry-run
# return.checkReturnEligibility
bidkit post-order return check-return-eligibility --format json --dry-run
# return.checkShippingLabelEligibility
bidkit post-order return check-shipping-label-eligibility RETURN-ID --format json
# return.createReturnDraft
bidkit post-order return create-return-draft --format json --dry-run
# return.createReturnRequest
bidkit post-order return create-return-request --format json --dry-run
# return.createReturnShippingLabel
bidkit post-order return create-return-shipping-label RETURN-ID --format json --dry-run
# return.deleteReturnDraftFile
bidkit post-order return delete-return-draft-file DRAFT-ID FILE-ID --format json --dry-run
# return.escalateReturn
bidkit post-order return escalate-return RETURN-ID --format json --dry-run
# return.getReturn
bidkit post-order return get-return RETURN-ID --format json
# return.getReturnDraft
bidkit post-order return get-return-draft DRAFT-ID --format json
# return.getReturnDraftFiles
bidkit post-order return get-return-draft-files DRAFT-ID --format json
# return.getReturnEstimate
bidkit post-order return get-return-estimate --format json --dry-run
# return.getReturnFiles
bidkit post-order return get-return-files RETURN-ID --format json
# return.getReturnPreferences
bidkit post-order return get-return-preferences --format json
# return.getReturnShippingLabel
bidkit post-order return get-return-shipping-label RETURN-ID --format json
# return.getShipmentTrackingInfo
bidkit post-order return get-shipment-tracking-info RETURN-ID --format json
# return.issueReturnRefund
bidkit post-order return issue-return-refund RETURN-ID --format json --dry-run
# return.markReturnReceived
bidkit post-order return mark-return-received RETURN-ID --format json --dry-run
# return.markReturnRefundReceived
bidkit post-order return mark-return-refund-received RETURN-ID --format json --dry-run
# return.markReturnRefundSent
bidkit post-order return mark-return-refund-sent RETURN-ID --format json --dry-run
# return.markReturnShipped
bidkit post-order return mark-return-shipped RETURN-ID --format json --dry-run
# return.processReturnRequest
bidkit post-order return process-return-request RETURN-ID --format json --dry-run
# return.search
bidkit post-order return search --limit 30 --format json
# return.sendReturnMessage
bidkit post-order return send-return-message RETURN-ID --format json --dry-run
# return.sendReturnShippingLabel
bidkit post-order return send-return-shipping-label RETURN-ID --format json --dry-run
# return.setReturnPreferences
bidkit post-order return set-return-preferences --format json --dry-run
# return.submitReturnFile
bidkit post-order return submit-return-file RETURN-ID --format json --dry-run
# return.updateReturnDraft
bidkit post-order return update-return-draft DRAFT-ID --format json --dry-run
# return.updateShipmentTrackingInfo
bidkit post-order return update-shipment-tracking-info RETURN-ID --format json --dry-run
# return.uploadReturnDraftFile
bidkit post-order return upload-return-draft-file RETURN-ID --format json --dry-run
# return.uploadReturnFile
bidkit post-order return upload-return-file RETURN-ID --format json --dry-run
# return.voidShippingLabel
bidkit post-order return void-shipping-label RETURN-ID --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
