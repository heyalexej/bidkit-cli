# Workflow: review open orders

Read-only survey of recent orders and their fulfillment state.

```bash
bidkit sell fulfillment get-orders --limit 50 --format json | jq '.orders[].orderId'

# one order's line items + shipping
bidkit sell fulfillment get-order 12-12345-12345 --format json

# the shipping label is a binary download (streamed, atomic)
bidkit sell logistics download-label-file SHIPMENT_ID --output-file label.pdf --force
```

Underlying keys: `sell_fulfillment.getOrders`, `sell_fulfillment.getOrder`,
`sell_logistics.downloadLabelFile`.

`downloadLabelFile` is a read but returns bytes — always use `--output-file` (raw mode embeds
no bytes in JSON).
