# Store API

- **Service key:** `sell_stores`
- **CLI:** `bidkit sell stores`
- **Version:** 1
- **Base path:** `/sell/stores/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_stores_v1_oas3.json`
- **Operations:** 8

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_stores.OPERATION_ID
bidkit api schema sell_stores.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_stores.addStoreCategory` | POST | `/store/categories` | unknown | This method is used to add a single new custom category to a user's eBay store through an  |
| `sell_stores.deleteStoreCategory` | DELETE | `/store/categories/{category_id}` | destructive | This method is used to delete one custom category of a user's eBay store through an asynch |
| `sell_stores.getStore` | GET | `/store` | read | This method is used to retrieve information for an eBay user's store such as store name, s |
| `sell_stores.getStoreCategories` | GET | `/store/categories` | read | This method is used to retrieve the category hierarchy for an eBay user's store. Note: Thr |
| `sell_stores.getStoreTask` | GET | `/store/tasks/{task_id}` | read | This method retrieves the current status of a recent store operation. The unique identifie |
| `sell_stores.getStoreTasks` | GET | `/store/tasks` | read | This method retrieves the status of all async store tasks for a store. Every task is set a |
| `sell_stores.moveStoreCategory` | POST | `/store/categories/move_category` | unknown | This method is used to move an existing user's eBay store custom category through an async |
| `sell_stores.renameStoreCategory` | PUT | `/store/categories/{category_id}` | write | This method is used to rename the single category of a user's eBay store through a synchro |

Command path prefix: `bidkit sell stores <operation>`.

## Examples

```bash
# sell_stores.addStoreCategory
bidkit sell stores add-store-category --body @request.json --format json --dry-run
# sell_stores.deleteStoreCategory
bidkit sell stores delete-store-category CATEGORY-ID --body @request.json --format json --dry-run
# sell_stores.getStore
bidkit sell stores get-store --format json
# sell_stores.getStoreCategories
bidkit sell stores get-store-categories --format json
# sell_stores.getStoreTask
bidkit sell stores get-store-task TASK-ID --format json
# sell_stores.getStoreTasks
bidkit sell stores get-store-tasks --format json
# sell_stores.moveStoreCategory
bidkit sell stores move-store-category --body @request.json --format json --dry-run
# sell_stores.renameStoreCategory
bidkit sell stores rename-store-category CATEGORY-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.
