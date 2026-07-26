# Agent instructions — bidkit-cli

`bidkit` is a CLI over the eBay REST APIs. **It talks to a real eBay seller
account.** Assume any command you run without `--dry-run` reaches production and
can create listings, end them, refund money, or message buyers. Read this before
running anything.

## Setting it up for someone

Install the executable (this package is **not** on PyPI):

```bash
uv tool install git+https://github.com/heyalexej/bidkit-cli   # or: uvx --from git+… bidkit --help
bidkit auth doctor        # always start here: says exactly what is missing
```

`auth doctor` is read-only and safe. If it reports `ready: true`, skip the rest.
Otherwise:

```bash
bidkit auth init          # writes ~/.config/bidkit/config.json (0600) with placeholders
bidkit auth login         # opens the browser, mints a user refresh token
bidkit auth login --write-config   # …and persists it
```

### What only the user can do — stop and ask

These steps are theirs, not yours. Say plainly what you need and why, then wait:

- **Supplying the eBay keyset** (`app_id`, `cert_id`, `ru_name`) from their
  developer account. You cannot invent or fetch these. `auth init` writes a
  file naming where each value comes from — point them at it.
- **Completing OAuth consent** in a browser and pasting back the redirect URL
  (`auth login` prints it; `--no-browser` if they prefer to open it themselves).
- **Granting additional scopes**, if `auth scopes` shows an operation's scope is
  missing — re-consent is a human action.
- **Business policies, inventory locations, and marketplace settings** that
  offers reference. These are account configuration, set up in Seller Hub.
- **Any decision to spend money or contact a buyer**: publishing a listing,
  issuing a refund, sending a message, leaving feedback. Propose it, show the
  `--dry-run` output, and let them decide.

Never print, echo, or commit credentials or tokens; never paste them into a
prompt sent to another service. If a task seems to need one, that is a signal to
hand back to the user, not to go looking for the file.

### Driving it from a script or another tool

Output is machine-readable by default when stdout is not a TTY. `--format json`
forces it, `--include-meta` wraps the payload as `{meta, data}` with the
operation, status and eBay request id, and `--select` projects a field out
(`--select "item_summaries[].title"`). Exit codes are stable and meaningful —
`0` success, `7` a safety refusal, `4` an eBay API error — so branch on them
rather than parsing text; the full table is in
`skills/bidkit-cli/references/output-and-errors.md`. Errors are emitted as JSON
on **stderr**, not stdout, which matters when you capture output.

## Safety model (read first)

Operations are classified in the manifest and gated accordingly:

- **Reads** run with no flag and are always safe.
- **Writes** require `--allow-write`.
- **Destructive** operations additionally require `--yes`.
- **Unclassified** (unknown-risk) mutations require `--allow-write-expert`.
- `--dry-run` validates and prints the request without sending it. Use it first
  whenever you are unsure; it needs no credentials and no network.

Never work around a gate — no `--allow-write-expert` to silence a refusal you do
not understand, and never add `--yes` just to stop a prompt. A refusal is
information.

Controlled test writes go through the test-mode gate and the durable run ledger:

```bash
bidkit --test-mode --test-run-id <purpose>-<YYYYMMDD> …
bidkit sell inventory test-run cleanup-report --run-id <id>
```

Test listings must use capital-letter-only SKUs (real inventory SKUs are
numeric), carry `[TEST]` in the title, and state in the description that nothing
will be shipped. **Clean up every test artifact**, and prove it: a record is gone
only when eBay answers **404**. A failed command is not proof of absence — a CLI
that cannot start looks identical to a deleted record if you only check whether
something came back.

## Scope

- **eBay REST only.** This CLI is a view over a generated manifest of eBay's
  REST operations (455 operations, 41 services). Do not add the legacy XML
  Trading API or any hand-written endpoint. If a task genuinely needs Trading,
  it belongs in a private script outside this repo.
- **`bidkit` (the SDK) is a dependency**, not part of this repo. Do not vendor,
  patch, or reach into it.
- **Never commit account-derived data**: SKUs, offer/listing/policy IDs, order
  data, buyer names, screenshots. Tests use obviously fake values
  (`SRC-A`, `TESTSKU000`, `358000000000`).

## Layout

| Path | What it is |
|---|---|
| `src/bidkit_cli/generated/manifest.json` | **generated** — the operation surface; never hand-edit |
| `src/bidkit_cli/session.py`, `session_revert.py` | session log recorder + revert planner |
| `src/bidkit_cli/dispatch.py` | the single choke point every operation flows through |
| `skills/bidkit-cli/SKILL.md` | the LLM-facing guide to the operation surface — **read this** |
| `scripts/regenerate_manifest.py` | rebuilds the manifest from a bidkit checkout |

The manifest is regenerated from the SDK, not written by hand, and CI proves it
reproduces byte-for-byte (`.github/workflows/manifest-drift.yml`). If your change
requires a manifest edit, regenerate it instead.

## Working style

- `uv` only — `uv run pytest -q`, `uv run ruff check src tests`. Never
  pip/poetry/conda.
- Before calling work done: tests and ruff both clean.
- This package is **not published to PyPI**; it installs with
  `uv tool install git+https://github.com/heyalexej/bidkit-cli`. Never add a
  publish workflow, and never add a `[tool.uv.sources]` path entry — a sibling
  path does not exist in a git clone and breaks that install. After any change
  to packaging metadata, verify the documented install in a clean environment;
  the test suite passes either way and will not catch it.
- Conventional Commits. Comments explain *why*, in timeless terms — never cite
  review rounds, tickets, or "recently changed".

## The session log

Every invocation appends JSONL records (invocation / gate / op / error / end) to
`$XDG_STATE_HOME/bidkit/sessions`, including the full per-attempt retry history
and eBay's request ids. It is a durable record, not a rotating log: nothing
expires on its own.

Export `BIDKIT_SESSION_ID` once and every command you run lands in one file, so
your work is inspectable afterwards:

```bash
export BIDKIT_SESSION_ID=$(uuidgen)
bidkit session show "$BIDKIT_SESSION_ID"     # what did I actually do?
bidkit session revert "$BIDKIT_SESSION_ID"   # plan to undo it (dry-run)
```

`revert` is honest about limits: compensating operations run, restoring a prior
state is not automated, and irreversible ones (booked fees, sent messages) are
always printed and never silently skipped. See
`skills/bidkit-cli/references/session-log.md`.

## If you are unsure

`bidkit api describe <operation>` prints an operation's parameters, request
model, and risk classification offline. `bidkit api examples <operation>` prints
runnable examples. Both are free — prefer them to guessing at a live call.
