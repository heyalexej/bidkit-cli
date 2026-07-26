# Deal API

- **Service key:** `buy_deal`
- **CLI:** `bidkit buy deal`
- **Version:** v1.3.0
- **Base path:** `/buy/deal/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_deal_v1_oas3.json`
- **Operations:** 4

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_deal.OPERATION_ID
bidkit api schema buy_deal.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_deal.getDealItems` | GET | `/deal_item` | read | This method retrieves a paginated set of deal items. The result set contains all deal item |
| `buy_deal.getEvent` | GET | `/event/{event_id}` | read | This method retrieves the details for an eBay event. The result set contains detailed info |
| `buy_deal.getEventItems` | GET | `/event_item` | read | This method returns a paginated set of event items. The result set contains all event item |
| `buy_deal.getEvents` | GET | `/event` | read | This method returns paginated results containing all eBay events for the specified marketp |

Command path prefix: `bidkit buy deal <operation>`.

## Examples

```bash
# buy_deal.getDealItems
bidkit buy deal get-deal-items --limit 30 --format json
# buy_deal.getEvent
bidkit buy deal get-event EVENT-ID --format json
# buy_deal.getEventItems
bidkit buy deal get-event-items --event-ids VALUE --limit 30 --format json
# buy_deal.getEvents
bidkit buy deal get-events --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
