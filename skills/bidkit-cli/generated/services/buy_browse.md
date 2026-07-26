# Browse API

- **Service key:** `buy_browse`
- **CLI:** `bidkit buy browse`
- **Version:** v1.20.4
- **Base path:** `/buy/browse/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_browse_v1_oas3.json`
- **Operations:** 7

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_browse.OPERATION_ID
bidkit api schema buy_browse.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_browse.checkCompatibility` | POST | `/item/{item_id}/check_compatibility` | unknown | This method checks if a product is compatible with the specified item. You can use this me |
| `buy_browse.getItem` | GET | `/item/{item_id}` | read | This method retrieves the details of a specific item, such as description, price, category |
| `buy_browse.getItemByLegacyId` | GET | `/item/get_item_by_legacy_id` | read | This method is a bridge between the eBay legacy APIs, such as Shopping and Finding , and t |
| `buy_browse.getItems` | GET | `/item/` | read | This method retrieves the details about specific items that buyers need to make a purchasi |
| `buy_browse.getItemsByItemGroup` | GET | `/item/get_items_by_item_group` | read | This method retrieves details about individual items in an item group. An item group is an |
| `buy_browse.search` | GET | `/item_summary/search` | read | This method searches for eBay items by various query parameters and retrieves summaries of |
| `buy_browse.searchByImage` | POST | `/item_summary/search_by_image` | read | This method searches for eBay items based on an image and retrieves summaries of the items |

Command path prefix: `bidkit buy browse <operation>`.

## Examples

```bash
# buy_browse.checkCompatibility
bidkit buy browse check-compatibility ITEM-ID --body @request.json --format json --dry-run
# buy_browse.getItem
bidkit buy browse get-item ITEM-ID --format json
# buy_browse.getItemByLegacyId
bidkit buy browse get-item-by-legacy-id --legacy-item-id VALUE --format json
# buy_browse.getItems
bidkit buy browse get-items --format json
# buy_browse.getItemsByItemGroup
bidkit buy browse get-items-by-item-group --item-group-id VALUE --format json
# buy_browse.search
bidkit buy browse search --q VALUE --limit 30 --format json
# buy_browse.searchByImage
bidkit buy browse search-by-image --body @request.json --limit 30 --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
