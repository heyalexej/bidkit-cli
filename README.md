# bidkit-cli

`bidkit` is the command-line interface for the [bidkit](https://github.com/heyalexej/bidkit)
eBay SDK. Every eBay REST operation represented by the checked-in OpenAPI specs is
callable from the shell: **41 services, 455 operations** across the `buy`,
`commerce`, `developer`, `post-order`, and `sell` namespaces.

The CLI is generated from the same normalized OpenAPI documents that generate the
Python client, so a shell command and an SDK call always agree. The command tree
is a view over a verified operation manifest, not a hand-written list — when an
operation is added upstream, it grows the tree automatically.

> **Status:** Alpha. The install path is `uv` from git; there is **no PyPI
> release** yet.

## Requirements

- Python **3.11** or newer.
- An eBay application keyset (`app_id`, `cert_id`, `ru_name`) and a user refresh
  token. `bidkit auth init` and `bidkit auth login` scaffold and mint these.

## Install

Install the `bidkit` executable with [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/heyalexej/bidkit-cli
```

…or run it ephemerally without installing anything:

```bash
uvx --from git+https://github.com/heyalexej/bidkit-cli bidkit --help
```

> `pip install bidkit-cli` / a PyPI package is **not** available for now. The
> dependency on the bidkit SDK is bounded to the `0.1.x` series because the
> command surface is generated against a specific SDK snapshot.

## Quick start

```bash
bidkit --help
bidkit auth init                       # write a skeleton config
bidkit auth login                      # mint a user refresh token (OAuth code flow)
bidkit auth doctor                     # read-only readiness + diagnostics

bidkit api list --namespace sell                       # discover (offline)
bidkit api describe sell_inventory.getInventoryItems   # full metadata (offline)
bidkit sell inventory get-inventory-items --limit 20   # call it directly
bidkit api call sell_inventory.getInventoryItems --query limit=20   # universal form
```

`describe`, `list`, `search`, `examples`, and `schema` are **offline** — no
client, no token, no network — so you can explore the whole surface safely.

## The command surface

Top-level groups: `api`, `auth`, `capabilities`, `config`, `sell`, `buy`,
`commerce`, `developer`, `post-order`, plus `version`, `completion`, and `skill`.

There are two equivalent ways to invoke any operation:

- **Direct** — the natural command path, best when you already know what you want:

  ```bash
  bidkit sell inventory get-inventory-items --limit 20
  bidkit sell fulfillment get-orders --query limit=30 --format json
  ```

- **Universal** — `bidkit api call` takes the stable **canonical operation key**
  (`namespace_service.operationId`). Use it to compose commands dynamically; it
  is the only dispatcher you ever need:

  ```bash
  bidkit api call sell_inventory.getInventoryItems --query limit=20 \
      --format json --include-meta
  ```

Discovery helpers:

```bash
bidkit api search "orders fulfillment"          # fuzzy search ids/paths/tags/summaries
bidkit api examples sell_fulfillment.getOrders  # copy-pasteable example commands
bidkit api schema sell_inventory.createOrReplaceInventoryItem request   # JSON Schema
```

## Safety model

Every operation is classified **read / write / destructive / unknown** from its
HTTP method, with hand-curated overrides for the canonical sell lifecycle.
Classification is enforced before any request is built.

| Risk         | Gate                                          |
|--------------|-----------------------------------------------|
| `read`       | runs normally                                 |
| `write`      | requires `--allow-write`                      |
| `destructive`| requires `--allow-write --yes`                |
| `unknown`    | fails closed — `--allow-write-expert --yes`   |
| `unknown` + external side effect | stays blocked even with the expert gate |

`--dry-run` is **always** allowed: it validates and prints the request without
sending it or acquiring a token. The canonical publish workflow
(`createOffer` → `publishOffer`) needs only `--allow-write`, not the expert
escape hatch.

```bash
# Preview a write without sending anything
bidkit sell inventory create-or-replace-inventory-item SKU --body @item.json --dry-run

# Execute a write
bidkit sell inventory create-offer --body @offer.json --allow-write

# Confirm resulting state with a read
bidkit sell inventory get-inventory-item SKU
```

## Output and errors

- **JSON when piped, a table when interactive.** Override with
  `--format json|table|text|raw`.
- `--select item_summaries[].item_id` projects a field out of a large response.
- `--include-meta` wraps JSON as `{meta, data}` with operation, status, and
  request id — useful for traceability.
- Binary responses stream atomically to `--output-file` (needs `--force` to
  overwrite).
- Secrets are redacted in every mode: tokens, `Authorization`, `Cookie`,
  signing/signature material, and sensitive query names
  (`token`/`secret`/`password`/`api-key`).

Errors are structured JSON with stable `kind` tags and machine-readable
classification, so the CLI is operable by humans **and** LLM agents.

**Exit codes** (part of the compatibility surface):

| Code | Meaning                                  |
|------|------------------------------------------|
| `0`  | success                                  |
| `1`  | expectation unmet (`verify-public`)      |
| `2`  | usage error                              |
| `3`  | config / auth error                      |
| `4`  | API error                                |
| `5`  | transport error                          |
| `6`  | validation error                         |
| `7`  | safety refusal                           |
| `8`  | I/O error                                |
| `9`  | internal error                           |
| `130`| interrupted                              |

Every JSON error carries a `kind`, an `exit_code`, and — where relevant —
`classification` (e.g. `invalid_request`, `not_found`, `account_not_eligible`),
`retryable`, and `retry_after` fields.

## Test-mode guardrails

For live experiments, the CLI adds opt-in containment:

- `--test-mode` requires a test marker, scramble consent, and a test-run id for
  traceability — a deliberate safety gate before publishing test listings.
- `bidkit sell inventory test-run` keeps a durable **ledger** (`init`, `record`,
  `show`, `execute --cleanup`, `cleanup-report`) so a controlled run records every
  SKU/offer/listing it creates and can be cleaned up deterministically. Writes
  made with `--test-run-id` auto-record.
- `bidkit sell inventory verify-public --listing-id … --expect not_found` asserts
  the public/Browse representation of a listing (the public API lags the seller
  API by minutes), so cleanup never reports success on a stale listing.

## Configuration and credentials

- Credentials live in `~/.config/bidkit/config.json` (a file at the legacy
  `~/.config/ebay-cli/` location is still read as a fallback).
- `bidkit auth init` writes a `0600` skeleton with placeholders and next-step
  hints; fill in the keyset from <https://developer.ebay.com/my/keys>, then
  `bidkit auth login`.
- `bidkit auth doctor` is a read-only readiness check (add `--check-network` to
  prove the app keyset, `--check-user-token` to prove seller consent — neither
  mutates account state).
- **Never commit credentials.** Keep `config.json` out of version control.

## Agent skill

A progressive-disclosure agent skill ships in the wheel under
`bidkit_cli/skill/`. An agent runtime loads it directly:

```bash
bidkit skill               # prints the installed SKILL.md location
```

The skill (`skills/bidkit-cli/SKILL.md` in this repo) documents the canonical
LLM workflow — discover → inspect → dry-run → execute → confirm — plus the
reference docs under `skills/bidkit-cli/references/`.

## Unofficial

bidkit and bidkit-cli are **unofficial** projects. They are not affiliated with,
endorsed by, or sponsored by eBay Inc. "eBay" is a trademark of eBay Inc.; this
project uses the term only to describe the public REST APIs it targets.

## License

[MIT](LICENSE) © bidkit contributors.
