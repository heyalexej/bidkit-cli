# CONTRACT — bidkit-cli session log (v1). All workers implement against this.

Repo: bidkit-cli (Python 3.11+, click, orjson, pydantic v2 available, uv only).
Style: `from __future__ import annotations`, full type hints, docstrings that
explain WHY in timeless terms. Never cite tickets/rounds. Line length 100.
Lint/format: `uv run ruff check src tests`. Tests: `uv run pytest -q`.

## Storage layout

Base dir resolution order:
1. `BIDKIT_SESSIONS_DIR` env var (expanduser), else
2. `$XDG_STATE_HOME/bidkit/sessions`, else
3. `~/.local/state/bidkit/sessions`

Files: `<base>/<YYYY-MM>/<YYYYMMDD>T<HHMMSS>Z_<session_id>.jsonl`
Spilled bodies: `<base>/bodies/<first2 of sha256>/<sha256>.json`
Dirs 0700, files 0600 (production PII).

`session_id` = 26-char Crockford base32 ULID-style: 10 chars of ms timestamp +
16 chars randomness, lexicographically sortable. `invocation_id` same generator.

## Record format (one JSON object per line, orjson, no indentation)

Common keys on EVERY record: `v` (=1), `type`, `ts` (UTC ISO-8601 with `Z`,
ms precision), `session_id`, `invocation_id`, `seq` (int, per-invocation,
starts at 0).

- `invocation`: `argv` (list[str], redacted), `cwd`, `env_fingerprint`
  ({cli_version, sdk_version, httpx2_version, python, platform}),
  `config_path`, `environment` ("production"/"sandbox"), `marketplace_id`,
  `test_run_id` (nullable), `caller` (env `BIDKIT_CALLER`, nullable),
  `dry_run` (bool), `parent_session_id` (nullable).
- `gate`: `operation_id`, `classification`, `allow_write`, `yes`, `dry_run`,
  `test_mode` (nullable dict {verdict, checks}), `confirmation` (nullable
  dict {prompted, answer}).
- `op`: `operation_id`, `classification`, `http` (dict: method, url, status,
  elapsed_ms_total, attempts=list), `ebay` (dict: request_id, rlogid),
  `request` ({params, body, body_ref, body_sha256}), `response` ({body,
  body_ref, body_sha256}), `ids` (dict), `test_run_id` (nullable),
  `pre_state` (nullable str), `reverse_hint` (nullable {op, args}),
  `irreversible` (bool), `compensates` (nullable {session_id, seq}).
- `error`: `operation_id` (nullable), `kind`, `message`, `status` (nullable),
  `request_id` (nullable), `http` (nullable, same shape as op.http).
- `end`: `exit_code`, `duration_ms`.

Attempt entry: `{"n": int, "status": int|null, "error": str|null,
"elapsed_ms": int, "ebay_request_id": str|null, "quota": {...}|null,
"retry": {...}|null}`.

Bodies: serialized size > 2048 bytes spills to a blob file and sets
`body_ref` + `body_sha256`, with `body: null`. Otherwise `body` is inline and
`body_ref` is null; `body_sha256` is ALWAYS set when a body exists.

## Public API of `src/bidkit_cli/session.py` (worker A owns this file)

```python
SCHEMA_VERSION: int = 1

def sessions_base_dir(override: str | None = None) -> Path
def new_id() -> str                       # ULID-style, see above
def redact_argv(argv: Sequence[str]) -> list[str]

class AttemptCollector:
    """Captures one entry per HTTP attempt, including SDK-internal retries.

    Installed as httpx2 event hooks on the client the CLI builds, because the
    SDK's retry loop is below the CLI: only the transport sees every attempt.
    """
    def request_hook(self, request: Any) -> None      # httpx2 event_hooks["request"]
    def response_hook(self, response: Any) -> None    # httpx2 event_hooks["response"]
    def note_transport_error(self, exc: BaseException) -> None
    def drain(self) -> list[dict[str, Any]]           # returns + clears attempts

class SessionRecorder:
    path: Path
    session_id: str
    invocation_id: str
    enabled: bool

    @classmethod
    def start(cls, *, base_dir: Path | None = None, session_id: str | None = None,
              invocation: dict[str, Any]) -> SessionRecorder: ...
    def record_gate(self, **fields: Any) -> None
    def record_op(self, **fields: Any) -> None
    def record_error(self, **fields: Any) -> None
    def finish(self, exit_code: int) -> None
    def attempts(self) -> AttemptCollector

class NullRecorder(SessionRecorder):   # no-op; used when logging is disabled
```

Semantics:
- `SessionRecorder.start` uses `BIDKIT_SESSION_ID` env when `session_id` is
  None; if that env names an existing session file, APPEND to it (reusing its
  session_id) with a fresh `invocation_id` and `seq` restarting at 0.
- **Fail-open**: every write is wrapped; on failure emit ONE stderr warning
  (`warning: session log unavailable: ...`) and disable further writes.
  Env `BIDKIT_SESSION_STRICT=1` re-raises instead (an unlogged write is worse
  than no write for some runs).
- Secrets never reach disk: redact via existing `bidkit_cli.redaction`
  (`redact_mapping`, `is_sensitive_name`); `redact_argv` masks the value of
  any `--token`-ish flag and anything matching a bearer/token shape.

## Reverse hints (worker A owns the table, worker D consumes it)

```python
REVERSE_OPS: dict[str, ReverseSpec]   # operation key -> spec
IRREVERSIBLE: dict[str, str]          # operation key -> reason
def reverse_hint_for(operation_key: str, *, ids: dict, params: dict) -> dict | None
def irreversible_reason(operation_key: str) -> str | None
```
Curated v1 table (only these; everything else -> None):
- `sell_inventory.createOrReplaceInventoryItem` -> `sell_inventory.deleteInventoryItem` args {sku}
- `sell_inventory.createOffer` -> `sell_inventory.deleteOffer` args {offer_id}
- `sell_inventory.createOrReplaceOffer`(if present) -> same as above
- `sell_inventory.publishOffer` -> `sell_inventory.withdrawOffer` args {offer_id}
- `sell_inventory.bulkPublishOffer` -> irreversible-by-tool (reason: "bulk publish must be withdrawn per offer")
IRREVERSIBLE (reason strings): any `sell_finances.*` mutation ("a booked fee cannot be reversed by deleting records"), `commerce_message.*` send ("a sent message cannot be unsent"), `sell_feedback.*` ("left feedback cannot be withdrawn by API").

## `src/bidkit_cli/session_revert.py` (worker D owns this file)

```python
@dataclass
class RevertStep:
    source_seq: int
    operation_key: str
    args: dict[str, Any]
    tier: Literal["compensating", "restoring", "irreversible", "unknown"]
    note: str | None

@dataclass
class RevertPlan:
    session_id: str
    session_path: Path
    steps: list[RevertStep]          # reverse-chronological, executable ones
    blocked: list[RevertStep]        # irreversible/unknown, reported never run

def build_plan(session_path: Path, *, only_last: int | None = None,
               only_seq: int | None = None) -> RevertPlan
def execute_plan(context: Any, plan: RevertPlan) -> list[dict[str, Any]]
```
`execute_plan` dispatches each step in-process through
`bidkit_cli.dispatch.execute` using `context.manifest.operation(key)`, mapping
`args` onto the operation's path params. It must record `compensates`
{session_id, seq} on each resulting op record (pass through the recorder on
the context). It stops at the first failure and returns results so far.

## `src/bidkit_cli/commands/session.py` (worker B owns this file)

Click group `session` with subcommands, all honoring `--format json`:
`list`, `show <session_id|path>`, `grep <pattern>`, `doctor`, `gc --keep-days N`,
`revert <session_id> [--last N] [--seq N] [--dry-run/--execute]`.
`revert` builds via `session_revert.build_plan`; execution requires
`--allow-write` (global) and `--yes`, prints blocked steps explicitly, and
never silently skips them. Exported symbol: `session_group`.

## Integration (worker C owns app.py / context.py / dispatch.py)

- `CliContext`: add `session_log: bool = True`, `sessions_dir: str | None`,
  `session_id: str | None`, `_recorder` field + `recorder` property returning
  a `SessionRecorder` (or `NullRecorder` when disabled).
- Global flags in `app.py`: `--no-session-log`, `--sessions-dir PATH`,
  `--session-id ID`. Register `session_group`. Start the recorder at
  invocation with the `invocation` record; `finish(exit_code)` in the same
  place the context is closed, including on error paths.
- `context.client`: build the `EbayClient` with an injected
  `httpx2.Client(timeout=..., event_hooks=collector hooks)` so retries are
  captured. Keep existing timeout semantics.
- `dispatch.execute`: emit the `gate` record after the safety/test-mode gates,
  and the `op` record after a successful dispatch (drain the collector for
  attempts; extract ids the same way `_record_test_event` does; attach
  reverse_hint/irreversible via `session.reverse_hint_for`). Emit `error`
  records for classified failures. Recording must NEVER change control flow or
  break the operation (best-effort, like the existing ledger recording).
