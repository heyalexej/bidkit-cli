# Item Feed Service

- **Service key:** `buy_feed`
- **CLI:** `bidkit buy feed`
- **Version:** v1_beta.35.3
- **Base path:** `/buy/feed/v1_beta`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `buy_feed_v1_beta_oas3.json`
- **Operations:** 4

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe buy_feed.OPERATION_ID
bidkit api schema buy_feed.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `buy_feed.getItemFeed` | GET | `/item` | read | This method lets you download a TSV_GZIP (tab-separated value gzip) Item feed file. The fe |
| `buy_feed.getItemGroupFeed` | GET | `/item_group` | read | This method lets you download a TSV_GZIP (tab separated value gzip) Item Group feed file.  |
| `buy_feed.getItemPriorityFeed` | GET | `/item_priority` | read | Using this method, you can download a TSV_GZIP (tab separated value gzip) Item Priority fe |
| `buy_feed.getItemSnapshotFeed` | GET | `/item_snapshot` | read | The Hourly Snapshot feed file is generated each hour every day for most categories. This m |

Command path prefix: `bidkit buy feed <operation>`.

## Examples

```bash
# buy_feed.getItemFeed
bidkit buy feed get-item-feed --feed-scope VALUE --category-id VALUE --accept VALUE --range VALUE --format json
# buy_feed.getItemGroupFeed
bidkit buy feed get-item-group-feed --feed-scope VALUE --category-id VALUE --accept VALUE --format json
# buy_feed.getItemPriorityFeed
bidkit buy feed get-item-priority-feed --category-id VALUE --date VALUE --accept VALUE --range VALUE --format json
# buy_feed.getItemSnapshotFeed
bidkit buy feed get-item-snapshot-feed --category-id VALUE --snapshot-date VALUE --accept VALUE --range VALUE --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
