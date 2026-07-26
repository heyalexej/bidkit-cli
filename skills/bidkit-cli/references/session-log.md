# Session log

Every CLI invocation is recorded to an **append-only JSONL trail** — a durable
record of what this account actually did, not a rotating ops log. Use it to
prove what you ran, diagnose eBay flakiness, and undo a botched write.

## Where it lives

- Default: `$XDG_STATE_HOME/bidkit/sessions` (falls back to
  `~/.local/state/bidkit/sessions`).
- Override with the `BIDKIT_SESSIONS_DIR` env var or the global `--sessions-dir PATH`.
- Disable per-invocation with the global `--no-session-log`.
- Layout: `<base>/<YYYY-MM>/<YYYYMMDD>THHMMSSZ_<session_id>.jsonl`, plus a shared
  `bodies/` tree for spilled request/response payloads.

Recording is **fail-open**: a write error warns once to stderr and disables the
recorder for the rest of that invocation; it never breaks a dispatch.

## Record types (one JSON object per line)

| Type         | Meaning                                                            |
|--------------|--------------------------------------------------------------------|
| `invocation` | One CLI process: argv (redacted), env, marketplace, format.        |
| `gate`       | A safety decision: the operation's risk class and the verdict.     |
| `op`         | One dispatched operation — the useful record. See below.           |
| `error`      | A classified API/transport failure, with the same attempt trail.   |
| `end`        | `exit_code` + `duration_ms`. Its absence means the process crashed.|

The `op` record carries:

- `operation_id` — the **canonical manifest key** (`sell_inventory.getInventoryItem`).
- `http.status` and `http.attempts` — a **per-attempt array** including every
  SDK-internal retry (status, elapsed_ms, error). This is the only vantage point
  that sees retries, because the SDK retries below the CLI.
- `ebay.request_id` (`x-ebay-c-request-id`) and `ebay.rlogid` — the correlation ids
  to paste into an eBay support trace.
- `ids` — resource ids extracted from path params / response body.
- `reverse_hint` — the compensating operation the revert planner will use, if any.

## Grouping invocations: `BIDKIT_SESSION_ID`

One session file can hold **many invocations**. When `BIDKIT_SESSION_ID` (or the
global `--session-id`) names an existing session, the recorder **appends** to it —
reusing its session id, minting a fresh invocation id, restarting `seq` at 0.
For a multi-step agent task, export it once per work stream so the whole trail
lands in one file:

```bash
export BIDKIT_SESSION_ID="refund-2026-07-26"   # any stable token; reused by every command in this task
```

## Inspecting (all read-only)

```bash
bidkit session list --since 7                    # newest-first: id, started, invocations, ops, env, exits
bidkit session show <id> --ops-only              # just the dispatched operations
bidkit session show <id> --format json           # the full record stream verbatim
bidkit session grep "createOffer|publishOffer"   # regex across all sessions; prints session/seq/type/match
bidkit session doctor                            # crashed invocations, corrupt lines, orphaned body blobs
```

`doctor` answers "is the log trustworthy?": an invocation whose last record is
not `end` crashed; corrupt lines are reported with file:line but never lose the
rest of the session; an orphaned blob is a spilled body file no session references.

## Reverting a session

```bash
bidkit session revert <id>                                     # dry-run: prints the compensating plan
bidkit session revert <id> --last 5 --execute --allow-write --yes   # run the last 5 compensating ops
bidkit session revert <id> --seq 42  --execute --allow-write --yes  # one recorded op
```

`revert` **prints a plan by default**. Executing is a real mutation, so it needs
the local `--execute` **plus** the global `--allow-write` and `--yes`. The plan
has three tiers, stated honestly:

- **Compensating ops run.** Only mutations with a clean, idempotent counterpart
  are mapped (e.g. `createOrReplaceInventoryItem`→`deleteInventoryItem`,
  `createOffer`→`deleteOffer`, `publishOffer`→`withdrawOffer`).
- **Restoring ops are not automated.** Anything without a mapping is reported as
  blocked with a reason, never silently no-op'd.
- **Irreversible ops are always printed, never skipped.** Booked fees
  (`sell_finances`), sent messages, and left feedback cannot be reversed by API;
  the plan lists them so you handle them out of band.

## Pruning space

Nothing expires on its own — **there is no retention policy**. Run `prune` bare
and it selects nothing and removes nothing. The default scope drops **spilled
body payloads** while every record line survives (a pruned session still reports
its operations, ids, status, retry history, and each body's sha256). Deleting
history itself takes `--records` plus an explicit range plus `--yes`.

```bash
bidkit session prune --older-than 90d            # preview bytes reclaimable (bodies only); deletes nothing
bidkit session prune --orphans --yes             # body blobs no session references (loses no history)
bidkit session prune --empty --older-than 1y --records --yes   # actually delete session files
```

A selection that would remove everything (a zero-length range) is refused.
`--keep-last N` (default `20`) floors the newest N sessions whatever else is
selected. Without `--yes`, `prune` previews what would go (bytes reclaimed) and
deletes nothing.

## When an agent should use this

- **Proving what you did** — `session show <id> --ops-only` is the auditable
  receipt of an operation sequence; quote `ebay.request_id` against a support case.
- **Diagnosing eBay flakiness** — the `http.attempts` array shows every retry,
  its status, and its error, which the single final response hides.
- **Undoing a botched write** — `session revert <id>` for a dry-run plan; execute
  only after reading the blocked/irreversible tiers.
