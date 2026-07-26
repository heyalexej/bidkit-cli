# Buy API namespace

Buyer-facing discovery APIs (item search, deals, marketing, market insights, offers, order).

```bash
bidkit buy browse search --q "vintage radio" --limit 5
bidkit buy browse get-item v1|1234567890
bidkit buy marketplace-insights search --q "tesla"
```

Common services: `browse`, `deal`, `feed`, `marketing`, `marketplace-insights`, `offer`, `order`.

## Member purchase history is NOT available

`buy_order` covers **guest checkout only** (`get-guest-checkout-session`,
`get-guest-purchase-order`). There is **no member (buyer) purchase-order**
operation in the current OAS surface and the configured OAuth scopes contain no
buyer-order scope, so member purchase history cannot be read from this CLI.

Check the capability explicitly:
```bash
bidkit buy purchases capability --format json
```

This reports `available: false` and the exact reason. **Never** infer "no
purchases" from a logged-out browser page, and **never** use
`sell_fulfillment.getOrders` to answer a purchase-history question — that
operation describes orders where this account is the **seller**, not purchases
made by the account.

### Data domains (do not confuse these)

| Domain | Service(s) | Side |
|---|---|---|
| seller sales | `sell_fulfillment`, `sell_finances` | this account is the seller |
| member purchases | _unavailable_ | this account is the buyer |
| guest checkout | `buy_order` | non-member buyer |
| feedback | `commerce_feedback` | either side |


`buy_browse.searchByImage` is a read-only POST (overridden in `safety.py`) — it runs without
`--allow-write`. Other POSTs in this namespace fail closed until classified.

List every operation:
```bash
bidkit api list --namespace buy --format json
```
