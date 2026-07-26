# Sell API namespace

Seller/account APIs: account, account-v2, analytics, compliance, feed, **finances** (signed),
**fulfillment** (orders/shipping/refunds), **inventory**, logistics, marketing, metadata,
recommendation, stores, and more.

```bash
bidkit sell inventory get-inventory-items --limit 20
bidkit sell inventory get-inventory-item SKU
bidkit sell fulfillment get-orders --limit 50
bidkit sell finances get-payouts
```

Notes:
- `sell_finances` (every operation) and `sell_fulfillment.issueRefund` require a signing key.
- `sell_inventory` has the most direct commands; inventory + offer + listing is the publish flow
  (see workflows/inventory-publish.md).
- `account` (v1) and `account-v2` are separate services on the CLI.
