# Negotiation API

- **Service key:** `sell_negotiation`
- **CLI:** `bidkit sell negotiation`
- **Version:** v1.1.2
- **Base path:** `/sell/negotiation/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_negotiation_v1_oas3.json`
- **Operations:** 2

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_negotiation.OPERATION_ID
bidkit api schema sell_negotiation.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_negotiation.findEligibleItems` | GET | `/find_eligible_items` | read | This method evaluates a seller's current listings and returns the set of IDs that are elig |
| `sell_negotiation.sendOfferToInterestedBuyers` | POST | `/send_offer_to_interested_buyers` | unknown | This method sends eligible buyers offers to purchase items in a listing at a discount. Whe |

Command path prefix: `bidkit sell negotiation <operation>`.

## Examples

```bash
# sell_negotiation.findEligibleItems
bidkit sell negotiation find-eligible-items --limit 30 --format json
# sell_negotiation.sendOfferToInterestedBuyers
bidkit sell negotiation send-offer-to-interested-buyers --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
