"""``bidkit session`` — inspect and manage the session log (CONTRACT v1).

The session log is an append-only JSONL trail of every CLI invocation and the
operations it dispatched. This group is read-only by default (``list``/``show``/
``grep``/``doctor``) plus two maintenance commands:

* ``gc`` removes session files older than a threshold, then sweeps body blobs
  that no remaining session references (blobs are *shared* across sessions, so a
  reference scan — not a per-file delete — is the only correct sweep).
* ``revert`` builds a compensating plan, and — with the safety gates — executes
  it. Blocked/irreversible steps are always printed, never silently skipped.

Two flags that read like local options are really the GLOBAL ``--dry-run`` /
``--allow-write`` / ``--yes`` (hoisted to the root group by the argv reorderer),
so they are read from ``ctx.obj`` rather than redeclared here. Redeclaring a
global option on a leaf command is a build-time error
(:func:`bidkit_cli.app._assert_no_global_option_collision`): the reorderer
would silently consume the value before the command ever saw it. ``revert``
therefore exposes a local ``--execute`` (default off = dry-run) instead of the
contract's ``--dry-run/--execute`` pair.

JSONL reading helpers live in this file (the on-disk format is fixed by the
contract), so the command module is importable and testable without the
recorder implementation in :mod:`bidkit_cli.session`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import click
import orjson

from ..context import CliContext
from ..errors import SafetyError, UsageError
from ..rendering import emit_json

_SESSION_GLOB = "*.jsonl"
_BLOB_GLOB = "*.json"
# Bodies spill at <base>/bodies/<first2 of sha256>/<sha256>.json; a blob whose
# serialized form is <= this stays inline. We never read bodies here — only
# their references — so the constant is documentary.
_BLOB_DIR = "bodies"


@click.group("session", help="Inspect and manage the session log.")
@click.pass_context
def session_group(ctx: click.Context) -> None:
    """Read the JSONL session log and (with gates) revert recorded operations.

    Reading the log does not extend it: inspecting sessions would otherwise
    create a session per look, so ``list`` would report a different count every
    time it ran and ``gc``/``doctor`` would inflate the very thing they audit.
    ``revert`` turns logging back on for itself — it performs real writes, and
    those must be recorded like any other mutation.
    """
    context = ctx.obj
    if context is not None:
        context.session_log = False


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@session_group.command("list")
@click.option("--since", type=int, default=None,
              help="Only sessions started within the last N days.")
@click.option("--limit", type=int, default=None,
              help="Cap the number of sessions shown (after newest-first sort).")
@click.pass_obj
def session_list(context: CliContext, since: int | None, limit: int | None) -> None:
    """List sessions newest-first: id, started, invocations, ops, env, mp, exits."""
    base = _base_dir(context)
    summaries = [_summarize(p) for p in _iter_session_files(base)]
    if since is not None:
        cutoff = datetime.now(UTC) - timedelta(days=since)
        # A session whose start time is unparseable is kept (never silently
        # hidden by --since); the filter only drops sessions known to be old.
        summaries = [s for s in summaries
                     if s.started_dt is None or s.started_dt >= cutoff]
    # Filenames are lexicographically sortable timestamps (CONTRACT), so a
    # name-descending sweep is a correct newest-first ordering.
    summaries.sort(key=lambda s: s.path.name, reverse=True)
    if limit is not None:
        summaries = summaries[: max(0, limit)]
    rows = [_summary_row(s) for s in summaries]
    payload: dict[str, Any] = {"count": len(rows), "sessions": rows}
    _emit(context, payload, lambda: _print_table(
        ["SESSION", "STARTED", "INV", "OPS", "ENV", "MARKETPLACE", "EXITS"],
        [[r["session_id"], r["started"] or "", r["invocations"], r["ops"],
          r["environment"] or "", r["marketplace"] or "",
          ",".join(str(c) for c in r["exit_codes"])] for r in rows],
        title=f"{len(rows)} session(s)",
    ))


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

@session_group.command("show")
@click.argument("session", required=True)
@click.option("--ops-only", is_flag=True, default=False,
              help="Only show op records (the dispatched operations).")
@click.pass_obj
def session_show(context: CliContext, session: str, ops_only: bool) -> None:
    """Show one session's records in order (human table by default).

    ``--format json`` emits the full record stream verbatim; ``--ops-only``
    restricts it to the ``op`` records regardless of format.
    """
    path = _resolve_session(_base_dir(context), session)
    records, errors = _read_records(path)
    if ops_only:
        records = [r for r in records if r.data.get("type") == "op"]
    payload: dict[str, Any] = {
        "session_id": _session_id_from_path(path),
        "path": str(path),
        "ops_only": ops_only,
        "records": [r.data for r in records],
        "parse_errors": errors,
    }
    _emit(context, payload, lambda: _print_records(records, errors))


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------

@session_group.command("grep")
@click.argument("pattern", required=True)
@click.option("--since", type=int, default=None,
              help="Only sessions started within the last N days.")
@click.pass_obj
def session_grep(context: CliContext, pattern: str, since: int | None) -> None:
    """Regex search across all session files; print session_id/seq/type/match."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise UsageError(f"invalid regex {pattern!r}: {exc}") from exc
    base = _base_dir(context)
    cutoff = datetime.now(UTC) - timedelta(days=since) if since is not None else None
    matches: list[dict[str, Any]] = []
    for path in _iter_session_files(base):
        if cutoff is not None:
            dt = _started_dt_from_path(path)
            if dt is not None and dt < cutoff:
                continue
        records, _errors = _read_records(path)
        for rec in records:
            blob = orjson.dumps(rec.data).decode()
            m = regex.search(blob)
            if m:
                matches.append({
                    "session_id": _session_id_from_path(path),
                    "seq": rec.data.get("seq"),
                    "type": rec.data.get("type"),
                    "match": _match_summary(rec.data, m),
                })
    payload: dict[str, Any] = {
        "pattern": pattern, "count": len(matches), "matches": matches,
    }
    _emit(context, payload, lambda: _print_table(
        ["SESSION", "SEQ", "TYPE", "MATCH"],
        [[mm["session_id"], mm["seq"], mm["type"], mm["match"]] for mm in matches],
        title=f"{len(matches)} match(es)",
    ))


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

@session_group.command("doctor")
@click.pass_obj
def session_doctor(context: CliContext) -> None:
    """Report crashed invocations, corrupt lines, and orphaned body blobs.

    An invocation is "crashed" when its final record is not ``end`` (the process
    died before recording its exit). Corrupt lines are reported with their file
    and line number but never lose the rest of the session. An orphaned blob is
    a spilled body file under ``bodies/`` that no session file references.
    """
    base = _base_dir(context)
    files = _iter_session_files(base)
    crashed: list[dict[str, Any]] = []
    corrupt: list[str] = []
    for path in files:
        records, errors = _read_records(path)
        corrupt.extend(errors)
        crashed.extend(_crashed_invocations(path, records))
    orphans = _orphaned_blobs(base, files)
    payload: dict[str, Any] = {
        "crashed_invocations": crashed,
        "corrupt_lines": corrupt,
        "orphaned_blobs": [str(p) for p in orphans],
    }
    _emit(context, payload, lambda: _print_doctor(payload))


# ---------------------------------------------------------------------------
# gc
# ---------------------------------------------------------------------------

@session_group.command("gc")
@click.option("--keep-days", type=int, required=True,
              help="Delete session files whose start time is older than N days.")
@click.pass_obj
def session_gc(context: CliContext, keep_days: int) -> None:
    """Delete old session files, then sweep orphaned body blobs.

    Preview vs. delete follows the GLOBAL ``--dry-run`` (``ctx.obj.dry_run``);
    it is not redeclared locally because that collides with the root-group
    option the argv reorderer already owns. The blob sweep scans references in
    the REMAINING session files (not the deleted ones): a body blob is shared
    across sessions and must survive as long as any one references it.
    """
    if keep_days < 0:
        raise UsageError("--keep-days must be >= 0")
    dry_run = bool(context.dry_run)
    base = _base_dir(context)
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    removed_sessions: list[str] = []
    kept: list[Path] = []
    for path in _iter_session_files(base):
        dt = _started_dt_from_path(path)
        if dt is not None and dt < cutoff:
            removed_sessions.append(str(path))
            if not dry_run:
                path.unlink(missing_ok=True)
        else:
            kept.append(path)
    removed_blobs: list[str] = []
    for blob in _orphaned_blobs(base, kept):
        removed_blobs.append(str(blob))
        if not dry_run:
            blob.unlink(missing_ok=True)
    payload: dict[str, Any] = {
        "dry_run": dry_run,
        "keep_days": keep_days,
        "removed_sessions": removed_sessions,
        "removed_blobs": removed_blobs,
        "kept_sessions": len(kept),
    }
    _emit(context, payload, lambda: _print_gc(payload))


# ---------------------------------------------------------------------------
# revert
# ---------------------------------------------------------------------------

@session_group.command("revert")
@click.argument("session", required=True)
@click.option("--last", "last_n", type=int, default=None,
              help="Only revert the last N executable operations.")
@click.option("--seq", "only_seq", type=int, default=None,
              help="Only revert the operation recorded at this seq number.")
@click.option("--execute", is_flag=True, default=False,
              help="Execute the plan. Default is a dry-run preview. Executing "
                   "requires the global --allow-write and --yes.")
@click.pass_obj
def session_revert(
    context: CliContext,
    session: str,
    last_n: int | None,
    only_seq: int | None,
    execute: bool,
) -> None:
    """Build (and with ``--execute`` + safety gates, run) a compensating plan.

    The contract's ``--dry-run/--execute`` pair is realized as a single local
    ``--execute`` flag (default off = dry-run): ``--dry-run`` is a global option
    that the root argv reorderer consumes before it could reach this command, so
    declaring it here is a build-time collision. Execution dispatches REAL
    compensating operations, so it additionally requires ``--allow-write`` and
    ``--yes``; blocked/irreversible steps are ALWAYS printed, never skipped.
    """
    # Refuse before importing/planning: the refusal must not depend on the
    # session_revert module being importable, and the gates are cheap to check.
    if execute:
        # The group disabled logging for inspection; an executing revert is a
        # real mutation and must leave its own trail (carrying `compensates`
        # back to the ops it undoes). Set before the recorder is first built.
        context.session_log = True
        if not context.allow_write:
            raise SafetyError(
                "revert --execute runs real compensating operations; "
                "pass --allow-write to permit writes.",
                risk="write",
            )
        if not context.yes:
            raise SafetyError(
                "revert --execute runs real compensating operations; "
                "pass --yes to confirm.",
                risk="write",
            )
    path = _resolve_session(_base_dir(context), session)
    # worker D owns session_revert; import lazily so this module stays
    # importable (and the dry-run refusal above stays reachable) without it.
    from ..session_revert import build_plan, execute_plan

    plan = build_plan(path, only_last=last_n, only_seq=only_seq)
    results: list[dict[str, Any]] = []
    if execute:
        results = execute_plan(context, plan)
    payload = _plan_payload(plan, executed=execute, results=results)
    _emit(context, payload, lambda: _print_plan(payload))


def _plan_payload(
    plan: Any, *, executed: bool, results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "session_id": plan.session_id,
        "session_path": str(plan.session_path),
        "executed": executed,
        "steps": [_step_payload(s) for s in plan.steps],
        # blocked steps are irreversible/unknown and are reported, never run;
        # they must always reach the caller so nothing is silently skipped.
        "blocked": [_step_payload(s) for s in plan.blocked],
        "results": results,
    }


def _step_payload(step: Any) -> dict[str, Any]:
    return {
        "source_seq": step.source_seq,
        "operation_key": step.operation_key,
        "args": step.args,
        "tier": step.tier,
        "note": step.note,
    }


# ---------------------------------------------------------------------------
# Storage helpers (on-disk format is fixed by CONTRACT; recorder-independent)
# ---------------------------------------------------------------------------

def _base_dir(context: CliContext) -> Path:
    """Resolve the sessions base directory (CONTRACT "Storage layout").

    Prefers the real resolver in :mod:`bidkit_cli.session` (worker A) and falls
    back to the documented order so this command module stays importable and
    testable before that dependency lands. An explicit override
    (``context.sessions_dir`` from the global ``--sessions-dir``) always wins.
    """
    override = getattr(context, "sessions_dir", None)
    try:
        from ..session import sessions_base_dir
    except ImportError:
        return _fallback_base_dir(override)
    return sessions_base_dir(override)


def _fallback_base_dir(override: str | None) -> Path:
    import os

    if override:
        return Path(override).expanduser()
    env = os.environ.get("BIDKIT_SESSIONS_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "bidkit" / "sessions"
    return Path.home() / ".local" / "state" / "bidkit" / "sessions"


def _iter_session_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    # *.jsonl never matches the *.json blobs under bodies/, so the glob cannot
    # accidentally descend into spilled bodies.
    return sorted(p for p in base.rglob(_SESSION_GLOB) if p.is_file())


@dataclass
class _SessionRecord:
    path: Path
    lineno: int
    data: dict[str, Any]


def _read_records(path: Path) -> tuple[list[_SessionRecord], list[str]]:
    """Parse a JSONL session file.

    Returns ``(records, parse_errors)``. Reading is best-effort: a single
    corrupt line is reported (with file:line) and skipped, never losing the
    records around it — doctor aggregates these errors across the whole store.
    """
    records: list[_SessionRecord] = []
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return records, [f"{path}: unreadable: {exc}"]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = orjson.loads(stripped)
        except orjson.JSONDecodeError as exc:
            errors.append(f"{path}:{lineno}: corrupt line: {exc.msg}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"{path}:{lineno}: non-object record")
            continue
        records.append(_SessionRecord(path=path, lineno=lineno, data=obj))
    return records, errors


def _resolve_session(base: Path, identifier: str) -> Path:
    """Resolve a session by id, filename, or absolute/under-base path."""
    candidate = Path(identifier)
    if candidate.is_file():
        return candidate
    under = base / identifier
    if under.is_file():
        return under
    matches = [
        p for p in _iter_session_files(base)
        if _session_id_from_path(p) == identifier
        or p.name == identifier or p.stem == identifier
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise UsageError(
            f"session id {identifier!r} matches {len(matches)} files; "
            "pass a full path to disambiguate"
        )
    raise UsageError(f"no session found for {identifier!r} under {base}")


def _session_id_from_path(path: Path) -> str:
    stem = path.stem
    return stem.split("_", 1)[1] if "_" in stem else stem


def _stamp_from_path(path: Path) -> str | None:
    stem = path.stem
    if "_" not in stem:
        return None
    return stem.split("_", 1)[0]


def _started_dt_from_path(path: Path) -> datetime | None:
    stamp = _stamp_from_path(path)
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _started_str_from_path(path: Path) -> str | None:
    dt = _started_dt_from_path(path)
    if dt is not None:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return _stamp_from_path(path)


# ---------------------------------------------------------------------------
# Summaries / analysis
# ---------------------------------------------------------------------------

@dataclass
class _SessionSummary:
    session_id: str
    path: Path
    started: str | None
    started_dt: datetime | None
    invocations: int
    op_count: int
    environment: str | None
    marketplace: str | None
    exit_codes: list[int]


def _summarize(path: Path) -> _SessionSummary:
    records, _errors = _read_records(path)
    invocations = sum(1 for r in records if r.data.get("type") == "invocation")
    op_count = sum(1 for r in records if r.data.get("type") == "op")
    exit_codes = [
        r.data["exit_code"] for r in records
        if r.data.get("type") == "end"
        and isinstance(r.data.get("exit_code"), int)
    ]
    environment: str | None = None
    marketplace: str | None = None
    session_id = _session_id_from_path(path)
    for rec in records:
        if rec.data.get("type") == "invocation":
            environment = rec.data.get("environment") or environment
            marketplace = rec.data.get("marketplace_id") or marketplace
            if rec.data.get("session_id"):
                session_id = str(rec.data["session_id"])
    return _SessionSummary(
        session_id=session_id,
        path=path,
        started=_started_str_from_path(path),
        started_dt=_started_dt_from_path(path),
        invocations=invocations,
        op_count=op_count,
        environment=environment,
        marketplace=marketplace,
        exit_codes=exit_codes,
    )


def _summary_row(s: _SessionSummary) -> dict[str, Any]:
    return {
        "session_id": s.session_id,
        "started": s.started,
        "invocations": s.invocations,
        "ops": s.op_count,
        "environment": s.environment,
        "marketplace": s.marketplace,
        "exit_codes": list(s.exit_codes),
        "path": str(s.path),
    }


def _match_summary(data: dict[str, Any], m: re.Match[str]) -> str:
    label = data.get("operation_id") or data.get("kind") or ""
    if data.get("type") == "invocation":
        argv = data.get("argv")
        if isinstance(argv, list):
            label = " ".join(str(a) for a in argv)
    snippet = m.group(0)
    if len(snippet) > 80:
        snippet = snippet[:77] + "..."
    prefix = f"{label}: " if label else ""
    return prefix + snippet


def _crashed_invocations(
    path: Path, records: list[_SessionRecord],
) -> list[dict[str, Any]]:
    """Invocations whose final record is not ``end`` (process died mid-run)."""
    last_type: dict[str, str] = {}
    order: list[str] = []
    for rec in records:
        inv = rec.data.get("invocation_id")
        if not inv:
            continue
        key = str(inv)
        if key not in last_type:
            order.append(key)
        last_type[key] = str(rec.data.get("type") or "")
    out: list[dict[str, Any]] = []
    for inv in order:
        if last_type[inv] != "end":
            out.append({
                "session_id": _session_id_from_path(path),
                "invocation_id": inv,
                "last_type": last_type[inv] or None,
                "path": str(path),
            })
    return out


def _ref_key(ref: Any) -> str:
    """Normalize a body_ref to the blob's sha key (the blob filename stem).

    ``body_ref`` is either the raw sha256 or a path ending in ``<sha>.json``;
    the blob file is ``<sha>.json`` whose stem is the sha.
    """
    text = str(ref)
    return Path(text).stem if text.endswith(".json") else Path(text).name


def _orphaned_blobs(base: Path, session_files: list[Path]) -> list[Path]:
    """Body blobs under ``bodies/`` referenced by none of ``session_files``."""
    bodies = base / _BLOB_DIR
    if not bodies.is_dir():
        return []
    all_blobs: dict[str, Path] = {
        p.stem: p for p in bodies.rglob(_BLOB_GLOB) if p.is_file()
    }
    referenced: set[str] = set()
    for path in session_files:
        for rec in _read_records(path)[0]:
            for side in ("request", "response"):
                container = rec.data.get(side)
                if isinstance(container, dict):
                    ref = container.get("body_ref")
                    if ref:
                        referenced.add(_ref_key(ref))
    return sorted(all_blobs[key] for key in all_blobs if key not in referenced)


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def _emit(
    context: CliContext, payload: dict[str, Any], render_human: Callable[[], None],
) -> None:
    if context.effective_format == "json":
        emit_json(payload, pretty=context.pretty)
    else:
        render_human()


def _print_table(
    columns: list[str], rows: list[list[Any]], *, title: str | None,
) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:  # pragma: no cover - rich is a hard dependency
        for row in rows:
            click.echo("\t".join("" if c is None else str(c) for c in row))
        return
    table = Table(title=title, show_lines=False, header_style="bold")
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*["" if c is None else str(c) for c in row])
    Console(highlight=False).print(table)


def _print_records(records: list[_SessionRecord], errors: list[str]) -> None:
    rows = [
        [r.data.get("seq"), r.data.get("type"), _record_label(r.data)]
        for r in records
    ]
    _print_table(["SEQ", "TYPE", "DETAIL"], rows, title=f"{len(rows)} record(s)")
    for err in errors:
        click.echo(f"warn: {err}", err=True)


def _record_label(data: dict[str, Any]) -> str:
    kind = data.get("type")
    if kind == "op":
        return str(data.get("operation_id") or "")
    if kind == "error":
        return str(data.get("kind") or data.get("message") or "")
    if kind == "end":
        return f"exit_code={data.get('exit_code')}"
    if kind == "invocation":
        argv = data.get("argv")
        return " ".join(str(a) for a in argv) if isinstance(argv, list) else ""
    if kind == "gate":
        return f"allow_write={data.get('allow_write')} yes={data.get('yes')}"
    return ""


def _print_doctor(payload: dict[str, Any]) -> None:
    crashed = payload["crashed_invocations"]
    corrupt = payload["corrupt_lines"]
    orphans = payload["orphaned_blobs"]
    click.echo(f"crashed invocations: {len(crashed)}")
    for c in crashed:
        click.echo(
            f"  {c['session_id']} invocation={c['invocation_id']} last={c['last_type']}"
        )
    click.echo(f"corrupt lines: {len(corrupt)}")
    for line in corrupt:
        click.echo(f"  {line}")
    click.echo(f"orphaned blobs: {len(orphans)}")
    for blob in orphans:
        click.echo(f"  {blob}")


def _print_gc(payload: dict[str, Any]) -> None:
    tag = "DRY RUN" if payload["dry_run"] else "DELETED"
    click.echo(f"[{tag}] removed sessions: {len(payload['removed_sessions'])}")
    for session in payload["removed_sessions"]:
        click.echo(f"  {session}")
    click.echo(f"[{tag}] removed blobs: {len(payload['removed_blobs'])}")
    for blob in payload["removed_blobs"]:
        click.echo(f"  {blob}")
    click.echo(f"kept sessions: {payload['kept_sessions']}")


def _print_plan(payload: dict[str, Any]) -> None:
    click.echo(f"session: {payload['session_id']}")
    click.echo(f"status: {'EXECUTED' if payload['executed'] else 'DRY RUN'}")
    click.echo(f"steps ({len(payload['steps'])}):")
    for step in payload["steps"]:
        note = f"  {step['note']}" if step["note"] else ""
        click.echo(
            f"  [{step['tier']}] seq={step['source_seq']} "
            f"{step['operation_key']} {step['args']}{note}"
        )
    # Blocked/irreversible steps are ALWAYS printed, never silently dropped.
    click.echo(f"blocked ({len(payload['blocked'])}):")
    for step in payload["blocked"]:
        note = f"  {step['note']}" if step["note"] else ""
        click.echo(
            f"  [{step['tier']}] seq={step['source_seq']} "
            f"{step['operation_key']}{note}"
        )


__all__ = ["session_group"]
