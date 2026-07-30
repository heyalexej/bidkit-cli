---
name: bidkit-cli
description: Drive the eBay REST APIs from the shell via the bidkit CLI. Discover, inspect, safely call, and verify any of the 452 generated operations across 40 services. Read-only by default; mutations require explicit --allow-write. Every invocation is recorded to an append-only session log you can inspect and, with gates, revert.
---

# bidkit CLI skill

**bidkit CLI** is the command-line interface for the [bidkit](https://github.com/heyalexej/bidkit)
eBay SDK — the public executable is `bidkit`, the Python distribution is `bidkit-cli`
(so it does not collide with the SDK it depends on). Every eBay REST operation
represented by the checked-in OpenAPI specs is callable: **40 services, 452
operations** (buy, commerce, developer, post-order, sell).

It is generated from the same normalized specs that generate the Python client, so a shell
command and an SDK call always agree. Canonical operation keys
(`sell_inventory.getInventoryItems`) are the stable identifier — use them in logs and task records.

## When to use this

- Run a quick read-only eBay query without writing Python.
- Inspect an operation's parameters, request model, or risk before calling it.
- Verify state after a mutation.
- Wire eBay calls into scripts/automation with stable, machine-readable JSON output.

## The 5 commands you need

```bash
bidkit api list --namespace sell                       # discover (offline)
bidkit api describe sell_inventory.getInventoryItem     # full metadata (offline)
bidkit api examples sell_fulfillment.getOrders          # copy-pasteable examples (offline)
bidkit api schema sell_inventory.createOrReplaceInventoryItem request  # JSON schema (offline)
bidkit sell inventory get-inventory-item SKU            # call it directly
```

Universal escape hatch — works for *any* of the 452 operations:

```bash
bidkit api call sell_inventory.getInventoryItems --query limit=20 --format json --include-meta
```

## Canonical LLM workflow (default to this)

```bash
# 1. Discover
bidkit api search "orders fulfillment" --format json
# 2. Inspect
bidkit api describe sell_fulfillment.getOrders
# 3. Examples / schema if you need inputs
bidkit api examples sell_fulfillment.getOrders
# 4. Execute a read-only request
bidkit api call sell_fulfillment.getOrders --query limit=30 --format json --include-meta
```

Prefer `api call` when composing commands dynamically (you only ever need the
stable canonical key). Use the shorter direct commands (`bidkit sell
fulfillment get-orders`) when the operation path is already known. **Always
request `--format json`** for agent/tool use, and add `--include-meta` when you
must preserve the request id / operation identity.

## Agent execution pattern (always follow this)

1. **Classify the task**: read-only or mutating? Check the operation's risk.
2. **`bidkit auth doctor`** if credentials/configuration are uncertain. Add
   `--check-network` to verify the app keyset (client token), or
   `--check-user-token` to verify the configured refresh token/seller consent
   (read-only — never mutates account state).
3. **Discover**: `api list` / `api search`.
4. **Inspect**: `api describe` / `api examples` / `api schema`.
5. **Build** request JSON/files locally.
6. **`--dry-run`** for any write or unfamiliar request (never sends, never acquires a token).
7. **Execute** with an explicit `--format json` (+ `--include-meta` for traceability).
8. **Preserve** the operation key + `x-ebay-c-request-id` in task records.
9. **Confirm** resulting state with a read operation.

## Safety (read this before any mutation)

Every operation is classified **read / write / destructive / unknown** from its HTTP method,
with hand-curated overrides for the canonical sell lifecycle:

- `read` → runs normally.
- `write` (PUT/PATCH, and the curated POSTs `createOffer`/`publishOffer`/
  `withdrawOffer`/`createImageFromFile`) → requires `--allow-write`.
- `destructive` (DELETE) → requires `--allow-write --yes`.
- `unknown` (an unclassified POST) → **fails closed** until classified, or forced with
  `--allow-write-expert --yes` (a deliberate two-gate expert action).
- `unknown` + external side effect (e.g. `commerce_notification.testSubscription`) →
  **stays blocked** even with `--allow-write-expert`; it triggers an observable external
  effect rather than a data mutation.

The canonical publish workflow (`createOffer` → `publishOffer`) therefore needs only
`--allow-write`, **not** the expert escape hatch. `--dry-run` is *always* allowed and
never touches the network.

## Capability discovery & test runs

- `bidkit capabilities list` — which generated operations this account can actually use
  (restricted/broken/stale surfaces only by default; `--all` for the full dump).
  `bidkit capabilities describe OP` explains one surface, with fuzzy suggestions on a typo.
- **What the current OAuth grant permits** — two axes, both offline:

  ```bash
  bidkit capabilities list --scope-blocked   # operations the configured scopes do NOT cover
  bidkit capabilities list --granted         # …and the ones they do
  bidkit auth doctor                         # `scope_coverage`: granted/blocked + missing scopes, ranked
  ```

  Scope coverage is separate from eBay's capability policy: an operation can be
  perfectly available and still unreachable for want of a scope. A missing scope
  is fixed by re-consenting (`auth login`) with the scope added, which is a user
  action — surface it rather than retrying into a 403.
- `bidkit auth doctor --show-capabilities` — capability snapshot alongside config diagnostics,
  with a first-install `ready`/`next_steps` block. `bidkit auth init` writes a skeleton config.
- `bidkit sell inventory test-run …` — a durable ledger for controlled test runs: `init`,
  `record`, `show`, `execute --cleanup` (idempotent withdraw+delete, gated by
  `--allow-write --yes`), and `cleanup-report`. Writes with `--test-run-id` auto-record.
- `bidkit sell inventory verify-public` — assert the public/Browse representation of a
  listing (`--expect active|visible|not_listed|not_found`), exits non-zero on an unmet
  expectation. Pass `--sku` to also read the seller side.

## Session log (audit trail)

Every invocation appends to an append-only JSONL trail under
`$XDG_STATE_HOME/bidkit/sessions`; inspect it, and (with gates) revert it.
Set `BIDKIT_SESSION_ID` once per work stream so a multi-step task shares one file.

```bash
bidkit session list --since 7                  # newest-first: id, started, invocations, ops, env, exits
bidkit session show <id> --ops-only            # the dispatched operations, in order
bidkit session grep "createOffer|publishOffer"  # regex across all sessions
bidkit session revert <id>                     # dry-run compensating plan (--execute needs --allow-write --yes)
```

See `references/session-log.md` for record types, inspecting, reverting, and pruning.

## Output

- Default is **JSON when piped, a table when interactive**. Pass `--format json|table|text|raw`.
- Use `--select` to project a field (e.g. `--select item_summaries[].item_id`).
- Binary responses stream to `--output-file PATH` atomically (needs `--force` to overwrite).
- Secrets never appear in any output mode: tokens, `Authorization`, `Cookie`,
  signing/signature, and sensitive query names (`token`/`secret`/`password`/
  `api-key`) are redacted by one shared policy across dry-run, raw, `--include-meta`,
  errors, and diagnostics.

## Exit codes

`0` ok · `2` usage · `3` config/auth · `4` API error · `5` transport · `6` validation · `7` safety · `8` I/O · `130` interrupted. `verify-public` exits `1` on an unmet expectation. See `references/output-and-errors.md` for the error taxonomy (`classification`/`retryable`/`retry_after`).

## Utility commands

| Command        | What it does                                                                  |
|----------------|-------------------------------------------------------------------------------|
| `config`       | Resolved config + precedence (`config show`); marketplace locales (`config locales`). |
| `capabilities` | Which generated operations this account can actually use (`capabilities list`/`describe`). |
| `version`      | Print CLI and SDK versions.                                                    |
| `skill`        | Print the location of the packaged agent skill.                                |
| `completion`   | Generate shell completion scripts (`completion {zsh|bash|fish}`).              |

## Go deeper (load only what you need)

- `references/session-log.md` — session log: record types, inspect, revert, prune.
- `references/authentication.md` — config, `auth doctor`/`login`, token cache, scopes.
- `references/configuration.md` — config file format, env vars, precedence.
- `references/output-and-errors.md` — formats, `--select`, raw mode, error shape.
- `references/safety-and-mutations.md` — risk classification, overrides, dry-run.
- `references/pagination.md` — limit/offset, the `members`/`items` conventions.
- `references/uploads-and-downloads.md` — JSON bodies, multipart, binary, streamed downloads.
- `references/services/` — one file per namespace (buy, commerce, developer, post-order, sell).
- `references/workflows/` — intent-level recipes (inventory publish, order review, refund, **public verification**).
- `generated/manifest-summary.md` — the generated operation/service inventory.

## Important capability limits

- **Member purchase history is unavailable.** `buy_order` covers guest checkout
  only; there is no member purchase-order operation or buyer scope. Check with
  `bidkit buy purchases capability`. Never confuse seller sales
  (`sell_fulfillment.getOrders`) with member purchases.
- **Public/Browse state lags the seller API.** After a delete the public listing
  can stay visible for minutes. Use `bidkit sell inventory verify-public
  --listing-id ... --expect not_found` (optionally `--sku`) to get an honest
  `stale_after_delete` result instead of a false green; cleanup must not report
  "fully cleaned" until it says `not_found` or `stale_after_delete`.

## Naming conventions

- Namespaces: `buy`, `commerce`, `developer`, `post-order`, `sell`.
- Services are kebab (`sell inventory`, `post-order return`).
- Operations are kebab method names (`get-inventory-items`).
- `return_` is exposed as `return`; `post_order` as `post-order`.
- The **canonical operation key** (`sell_inventory.getInventoryItems`) is the stable identifier — use it in logs and task records.
