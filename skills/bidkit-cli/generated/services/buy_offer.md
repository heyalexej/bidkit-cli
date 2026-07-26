# Buy Offer API

- **Service key:** `buy_offer`
- **CLI:** `bidkit buy offer`
- **Version:** v1_beta.0.1
- **Base path:** `/buy/offer/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_offer_v1_beta_oas3.json`
- **Operations:** 2

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_offer.OPERATION_ID
bidkit api schema buy_offer.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_offer.getBidding` | GET | `/bidding/{item_id}` | read | This method retrieves the bidding details that are specific to the buyer of the specified  |
| `buy_offer.placeProxyBid` | POST | `/bidding/{item_id}/place_proxy_bid` | unknown | This method uses a user access token to place a proxy bid for the buyer on a specific auct |

Command path prefix: `bidkit buy offer <operation>`.

## Examples

```bash
# buy_offer.getBidding
bidkit buy offer get-bidding ITEM-ID --format json
# buy_offer.placeProxyBid
bidkit buy offer place-proxy-bid ITEM-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
