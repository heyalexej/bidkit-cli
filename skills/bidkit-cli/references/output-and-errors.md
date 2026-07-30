# Output, selection, and errors

## Formats

`--format json|table|text|raw`. Default is **JSON when piped, table when a TTY**.

- `json` — canonical, machine-readable. `--compact` for no indentation.
- `table` — a conservative view; **never drops fields** (fall back to JSON if no projection).
- `text` — plain text (for text responses).
- `raw` — `{status, headers, body}`; useful for diagnosing.

Preserve eBay wire aliases (`itemId`, not `item_id`) via `model_dump(by_alias=True)`.

## Selection

```bash
bidkit buy browse search --q "radio" --select item_summaries
bidkit buy browse search --q "radio" --select 'item_summaries[].item_id'
```

`--select` is a tiny dotted path with an optional trailing `[]` to unwrap a list. It is **not**
a query language (jq is intentionally not a core dependency).

## Response metadata (`--include-meta`)

Wrap the JSON payload in `{meta, data}` so an agent can preserve operation
identity, status, and request id:

```bash
bidkit sell fulfillment get-orders --limit 30 --format json --include-meta
```

```json
{
  "meta": {
    "operation": "sell_fulfillment.getOrders",
    "http_method": "GET",
    "path": "/order",
    "status": 200,
    "request_id": "..."
  },
  "data": { "orders": [] }
}
```

`--include-meta` only affects JSON output; `--format raw` keeps its own envelope.
The request id is read from `x-ebay-c-request-id` / `x-ebay-request-id`, falling
back to `x-traffic-request-id` when eBay returned no dedicated request id. The
raw traffic id is also exposed as `trace_id`. **No** authorization, cookie, or
signing headers are ever included. For binary streams (`--output-file`), `meta`
adds `status`, `request_id`, and `trace_id` to the file summary.

## Saving output

```bash
bidkit sell logistics download-label-file SHIPMENT_ID --output-file label.pdf --force
```

`--output-file` writes atomically (temp + rename), never overwrites without `--force`, and
streams binary responses instead of loading them into memory.

## Empty / 204 responses

JSON mode emits `null`; human mode prints a concise success message.

## Error shape (stable, JSON mode)

```json
{
  "error": {
    "kind": "api_error",
    "message": "...",
    "operation": "sell_inventory.deleteInventoryItem",
    "status": 404,
    "classification": "not_found",
    "retryable": false,
    "hint": "The resource/route is absent, stale, or no longer applicable; do not retry."
  }
}
```

`kind` values: `usage_error`, `manifest_error`, `config_error`, `api_error`,
`transport_error`, `validation_error`, `safety_error`, `io_error`. A
`safety_error` additionally carries `risk` (the effective risk that triggered
the refusal).

### Error taxonomy (stable, machine-readable)

Every API/transport failure carries a `classification` plus `retryable` (and
`retry_after` for rate limits) so an agent decides remediation deterministically
instead of scraping prose. The HTTP status is the primary signal; the body is a
hint, never an override.

| classification | status | meaning | retry? |
| --- | --- | --- | --- |
| `invalid_request` | 400 | Required input, enum, pagination, or filter wrong | No |
| `unauthenticated` | 401 (default) | Token expired/insufficient; refresh or re-consent | Yes |
| `account_not_eligible` | 401 (policy) | Account cannot call this account-restricted product (e.g. eDIS) | No |
| `capability_not_granted` | 403 | Scope, membership, partner approval, or subscription missing | No |
| `not_found` | 404 | Resource/route absent, stale, or not applicable | No |
| `rate_limited` | 429 | eBay requested backoff (honor `retry_after`) | Yes |
| `upstream_error` | 500 | eBay failed after receiving a valid request | Bounded |
| `transport_error` | timeout/network | Request did not complete reliably | Bounded |

For a non-JSON (HTML) upstream failure the full page is **not** echoed; instead
a bounded `normalized_body` carries `{status, operation, request_id,
content_type, body_preview}` (≤280 chars). A failed write/destructive call
additionally gets the non-idempotency note: "remote state may have changed —
re-read before retrying." The capability policy suppresses retries on surfaces
known to fail for this account (Leads, VeRO, eDIS, Buy bulk/Deal/Marketing), so a 500 on
those is `retryable: false`. Use `bidkit capabilities list` to see which.

The error shape follows the *requested* `--format`, not stdout's TTY-ness:
`--format json` emits a JSON error on a TTY; `--format text` emits a text error
when piped. Text mode still surfaces `classification`/`retryable`/`retry_after`.

## Secret redaction (all modes)

A single shared policy redacts sensitive values everywhere output is produced:
dry-run previews, `--format raw` response headers, `--include-meta`, errors, and
diagnostics. Names matched (case-insensitive) include `authorization`, `cookie`,
`set-cookie`, `token`, `secret`, `password`, `api-key`/`apikey`, `signature`, and
`x-ebay-c-enduserctx`. The key is preserved with a `<redacted>` marker so a
reviewer can see *which* value was sent, never its contents.

## Exit codes

`0` ok · `2` usage · `3` config/auth · `4` API error · `5` transport · `6` validation ·
`7` safety · `8` I/O · `130` interrupted (Ctrl-C, including a prompt abort).

An assertion-style verifier (`sell inventory verify-public`) exits `1` when the
requested expectation is not met; the full JSON report still goes to stdout.

All diagnostics go to **stderr**; successful data to **stdout**.
