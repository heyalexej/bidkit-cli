# Safety and mutations

The CLI **fails closed** for anything that can change seller/account state.

## Risk classification (from HTTP method)

| Method          | Risk           |
|-----------------|----------------|
| GET/HEAD/OPTIONS | `read`         |
| PUT/PATCH       | `write`        |
| DELETE          | `destructive`  |
| POST            | `unknown` (fails closed by default) |

POST is `unknown` because eBay uses POST for both searches (safe) and mutations. Known
read-only POSTs are overridden in `bidkit_cli/safety.py`; everything else stays blocked
until classified.

## Invocation policy

- `read` → runs normally.
- `write` → `--allow-write`.
- `destructive` → `--allow-write --yes`.
- `unknown` (unclassified POST) → refuses; force with `--allow-write-expert --yes`.
  The CLI cannot know whether an unclassified POST mutates state, so forcing it
  is a deliberate **two-gate** expert action — the flag *and* the confirmation.
- `unknown` (external side effect, e.g. `commerce_notification.testSubscription`)
  → **stays blocked** even with `--allow-write-expert`. It is not a data mutation
  but has an observable external effect; the hint says so instead of implying the
  flag will force it.

## Dry-run (always allowed, never sends)

```bash
bidkit sell inventory create-or-replace-inventory-item TEST-SKU \
  --body @item.json --dry-run
```

Prints the resolved method, URL, path/query params, a **redacted** body shape, auth scheme,
signing requirement, and risk. Never acquires a token; never sends a request.

## Adding a read-only POST

If a `POST` is genuinely read-only, add a `RiskOverride(... classification="read_only")`
entry to `_OVERRIDES` in `bidkit_cli/safety.py` with a specific reason, so a
reviewer can confirm it. Operations with external side effects (e.g. triggering
a notification) use `classification="external_side_effect"` — they stay blocked
but with a clear reason. `validate_overrides(manifest)` fails the test suite if
any key goes stale.

## Examples

```bash
# read — no flags
bidkit sell inventory get-inventory-items --limit 20

# write
bidkit sell inventory create-or-replace-inventory-item SKU --body @item.json --allow-write

# destructive
bidkit sell inventory delete-inventory-item SKU --allow-write --yes

# unknown POST you have confirmed is safe (two gates)
bidkit sell fulfillment issue-refund ORDER --body @refund.json --allow-write-expert --yes

# copy-pasteable examples for any operation (offline)
bidkit api examples sell_fulfillment.getOrders
```
