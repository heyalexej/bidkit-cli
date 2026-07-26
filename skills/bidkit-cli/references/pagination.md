# Pagination

eBay list endpoints use `limit`/`offset` (or `offset`/`limit`) query params and return a
collection under a service-specific array field.

## Common conventions

| Service                | Array field          |
|------------------------|----------------------|
| sell_inventory         | `inventoryItems`     |
| sell_fulfillment       | `orders`             |
| sell_marketing         | `campaigns` / `reports` |
| buy_browse (search)    | `itemSummaries`      |
| post-order (search)    | `members`            |

## Iterate with the CLI

```bash
bidkit sell inventory get-inventory-items --limit 100 --offset 0 --format json \
  | jq '.inventoryItems[].sku'

# page forward
bidkit sell inventory get-inventory-items --limit 100 --offset 100
```

`limit`/`offset` are typed as strings in eBay's specs but accept integers; the CLI coerces
them (the generated method signature accepts `int | str`).

## In Python

The SDK ships `bidkit.paginate` / `paginate_async` for cursor-free iteration:

```python
from bidkit import EbayClient, paginate
for item in paginate(client.sell.inventory.get_inventory_items, limit=100):
    ...
```

(From the shell, script the loop; the CLI does not auto-paginate in v1.)

## Tips

- `--select` can pull just the IDs from one page:
  `--select 'inventoryItems[].sku'`.
- Total counts usually live next to the array (`total`, `totalNumberOfCases`, etc.).
