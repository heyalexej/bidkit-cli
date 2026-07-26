# Finances API

- **Service key:** `sell_finances`
- **CLI:** `bidkit sell finances`
- **Version:** v1.19.0
- **Base path:** `/sell/finances/v1`  ·  **Subdomain:** `apiz`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** True
- **Source spec:** `sell_finances_v1_oas3.json`
- **Operations:** 11

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_finances.OPERATION_ID
bidkit api schema sell_finances.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_finances.getBillingActivities` | GET | `/billing_activity` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getOrderEarnings` | GET | `/order_earnings` | read | This method returns detailed order-level financial data for each order associated with a s |
| `sell_finances.getOrderEarningsById` | GET | `/order_earnings/{order_id}` | read | This method returns detailed order-level financial data including order earnings, gross am |
| `sell_finances.getOrderEarningsSummary` | GET | `/order_earnings_summary` | read | This method returns a summarized view of order earnings information for one or more orders |
| `sell_finances.getPayout` | GET | `/payout/{payout_Id}` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getPayoutSummary` | GET | `/payout_summary` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getPayouts` | GET | `/payout` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getSellerFundsSummary` | GET | `/seller_funds_summary` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getTransactionSummary` | GET | `/transaction_summary` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getTransactions` | GET | `/transaction` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |
| `sell_finances.getTransfer` | GET | `/transfer/{transfer_Id}` | read | Important! Due to EU & UK Payments regulatory requirements, an additional security verific |

Command path prefix: `bidkit sell finances <operation>`.

## Examples

```bash
# sell_finances.getBillingActivities
bidkit sell finances get-billing-activities --limit 30 --format json
# sell_finances.getOrderEarnings
bidkit sell finances get-order-earnings --limit 30 --format json
# sell_finances.getOrderEarningsById
bidkit sell finances get-order-earnings-by-id ORDER-ID --format json
# sell_finances.getOrderEarningsSummary
bidkit sell finances get-order-earnings-summary --format json
# sell_finances.getPayout
bidkit sell finances get-payout PAYOUT-ID --format json
# sell_finances.getPayoutSummary
bidkit sell finances get-payout-summary --format json
# sell_finances.getPayouts
bidkit sell finances get-payouts --limit 30 --format json
# sell_finances.getSellerFundsSummary
bidkit sell finances get-seller-funds-summary --format json
# sell_finances.getTransactionSummary
bidkit sell finances get-transaction-summary --filter "transactionDate:[2024-01-01T00:00:00.000Z..]" --format json
# sell_finances.getTransactions
bidkit sell finances get-transactions --limit 30 --format json
# sell_finances.getTransfer
bidkit sell finances get-transfer TRANSFER-ID --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
