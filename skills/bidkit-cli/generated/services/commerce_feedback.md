# Feedback API

- **Service key:** `commerce_feedback`
- **CLI:** `bidkit commerce feedback`
- **Version:** v1.0.0
- **Base path:** `/commerce/feedback/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_feedback_v1_beta_oas3.json`
- **Operations:** 5

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_feedback.OPERATION_ID
bidkit api schema commerce_feedback.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_feedback.getFeedback` | GET | `/feedback` | read | This method enables users to retrieve feedback for any specified user ID and feedback type |
| `commerce_feedback.getFeedbackRatingSummary` | GET | `/feedback_rating_summary` | read | This method provides a detailed overview of feedback ratings associated with a user in the |
| `commerce_feedback.getItemsAwaitingFeedback` | GET | `/awaiting_feedback` | read | This method retrieves line items awaiting feedback from the user's order partner. You can  |
| `commerce_feedback.leaveFeedback` | POST | `/feedback` | unknown | This method creates and submits feedback to the user's order partner for a line item in th |
| `commerce_feedback.respondToFeedback` | POST | `/respond_to_feedback` | unknown | This method allows users to respond to feedback provided by the order partner for a specif |

Command path prefix: `bidkit commerce feedback <operation>`.

## Examples

```bash
# commerce_feedback.getFeedback
bidkit commerce feedback get-feedback --feedback-type VALUE --user-id VALUE --limit 30 --format json
# commerce_feedback.getFeedbackRatingSummary
bidkit commerce feedback get-feedback-rating-summary --filter VALUE --user-id VALUE --format json
# commerce_feedback.getItemsAwaitingFeedback
bidkit commerce feedback get-items-awaiting-feedback --limit 30 --format json
# commerce_feedback.leaveFeedback
bidkit commerce feedback leave-feedback --body @request.json --format json --dry-run
# commerce_feedback.respondToFeedback
bidkit commerce feedback respond-to-feedback --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
