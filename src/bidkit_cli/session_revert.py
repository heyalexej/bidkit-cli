"""Session revert: build and execute a compensating plan from a session log.

A session log is an append-only JSONL trail of what the CLI actually did. To
"undo" a session we replay it in reverse, substituting each recorded operation
with a compensating counterpart (``publishOffer`` -> ``withdrawOffer``,
``createOffer`` -> ``deleteOffer``, ...) where the reverse table knows one, and
surfacing the rest as *blocked* with a per-step reason instead of silently
dropping them. Executing a plan re-dispatches each compensating operation
in-process so the very same auth, retry, safety, and recording path that
produced the original session also records its reversal and links the two via
``compensates``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import orjson

from .dispatch import execute

__all__ = ["RevertStep", "RevertPlan", "build_plan", "execute_plan"]


@dataclass
class RevertStep:
    """One action derived from a single recorded op.

    ``tier`` decides what a caller may do with the step: only ``compensating``
    steps are executable. The remaining tiers exist so the CLI can report,
    per step, *why* it was not run — an undo that quietly omits half a session
    is worse than one that refuses loudly.
    """

    source_seq: int
    operation_key: str
    args: dict[str, Any]
    tier: Literal["compensating", "restoring", "irreversible", "unknown"]
    note: str | None = None


@dataclass
class RevertPlan:
    """A reverse-chronological view of a session split into runnable vs blocked.

    ``steps`` holds the compensating actions in the order they must run (newest
    op first); ``blocked`` holds everything we deliberately do not run, each
    with a note explaining why. Keeping the two lists separate makes the
    "never silently skip a step" contract in the ``session revert`` command
    trivial to honour.
    """

    session_id: str
    session_path: Path
    steps: list[RevertStep] = field(default_factory=list)
    blocked: list[RevertStep] = field(default_factory=list)


def _load_op_records(session_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Read a session JSONL, returning ``(session_id, op records in file order)``.

    The session id is taken from the first record that carries one — every
    record is required to. Op records are kept in on-disk (chronological) order
    so the caller can reverse them in one place. The file is opened in binary
    mode and parsed line by line so a large session never holds two copies in
    memory at once.
    """
    session_id = ""
    ops: list[dict[str, Any]] = []
    with session_path.open("rb") as handle:
        for raw in handle:
            stripped = raw.strip()
            if not stripped:
                continue
            record = orjson.loads(stripped)
            if not session_id and record.get("session_id"):
                session_id = record["session_id"]
            if record.get("type") == "op":
                ops.append(record)
    if not session_id:
        raise ValueError(f"session {session_path} carries no session_id")
    return session_id, ops


def _operation_key(record: dict[str, Any]) -> str:
    """Best-effort canonical operation key from an op record.

    The op record's primary identifier is ``operation_id``; we also accept an
    explicit ``operation_key``/``key`` if a future recorder emits one, so this
    module keeps working without a coordinated change across workers.
    """
    return (
        record.get("operation_key")
        or record.get("key")
        or record.get("operation_id")
        or ""
    )


def build_plan(
    session_path: Path,
    *,
    only_last: int | None = None,
    only_seq: int | None = None,
) -> RevertPlan:
    """Build a reverse plan from a session log.

    The session is walked newest-op-first. For each op we ask the reverse table
    (in :mod:`bidkit_cli.session`) for a compensating operation; ops the table
    cannot reverse are still surfaced, classified by *why*:

    * a recorded prior state (``pre_state`` blob ref) with no reverse mapping is
      ``restoring`` — fully automatable in principle, but v1 does not replay
      arbitrary state snapshots, so it is blocked with an explicit note;
    * an operation flagged irreversible (e.g. a sent message) is ``irreversible``
      and blocked with the table's human reason;
    * anything else is ``unknown`` and blocked, so the CLI reports it rather than
      silently dropping it from the undo.

    ``only_last`` narrows the window to the N newest ops; ``only_seq`` selects a
    single seq. They are mutually exclusive because combining "the last N" with
    "a specific seq" is ambiguous and has no useful intersection.

    The source file is only ever read: this function never writes, truncates, or
    otherwise mutates the session log.
    """
    if only_last is not None and only_seq is not None:
        raise ValueError("only_last and only_seq are mutually exclusive")

    # Deferred import: the reverse table lives in session.py, a sibling module
    # owned by another worker that may not yet be present in every checkout.
    # Keeping the import local lets the dataclasses and execute_plan stay
    # importable on their own, and surfaces this dependency only when a plan is
    # actually built.
    from .session import irreversible_reason, reverse_hint_for

    session_id, ops = _load_op_records(session_path)

    # Reverse-chronological: records are appended in order, so the newest op is
    # the last line on disk.
    ordered = list(reversed(ops))

    if only_last is not None:
        if only_last < 0:
            raise ValueError("only_last must be non-negative")
        ordered = ordered[:only_last]
    elif only_seq is not None:
        ordered = [record for record in ordered if record.get("seq") == only_seq]

    steps: list[RevertStep] = []
    blocked: list[RevertStep] = []
    for record in ordered:
        # An op without a seq cannot be correlated back to a compensates link;
        # use a sentinel so it is still reported rather than silently dropped.
        source_seq = record.get("seq")
        if source_seq is None:
            source_seq = -1
        key = _operation_key(record)
        ids = record.get("ids") or {}
        request = record.get("request") or {}
        params = request.get("params") or {}

        hint = reverse_hint_for(key, ids=ids, params=params) if key else None
        if hint:
            steps.append(RevertStep(
                source_seq=source_seq,
                operation_key=hint.get("op") or key,
                args=dict(hint.get("args") or {}),
                tier="compensating",
                note=None,
            ))
            continue

        if record.get("pre_state"):
            blocked.append(RevertStep(
                source_seq=source_seq,
                operation_key=key,
                args={},
                tier="restoring",
                note="restoring a prior state is not automated yet",
            ))
            continue

        reason = irreversible_reason(key) if key else None
        if reason:
            blocked.append(RevertStep(
                source_seq=source_seq,
                operation_key=key,
                args={},
                tier="irreversible",
                note=reason,
            ))
            continue

        blocked.append(RevertStep(
            source_seq=source_seq,
            operation_key=key,
            args={},
            tier="unknown",
            note="no reverse mapping for this operation",
        ))

    return RevertPlan(
        session_id=session_id,
        session_path=session_path,
        steps=steps,
        blocked=blocked,
    )


def _path_params_for(operation: Any, args: dict[str, Any]) -> dict[str, str]:
    """Map reverse-hint args (python names) onto an operation's path params.

    Reverse hints name their args in snake_case (``offer_id``, ``sku``) while
    :func:`bidkit_cli.dispatch.execute` consumes path params keyed by wire name
    (``offerId``, ``sku``). Walking the operation's declared path params — rather
    than trusting the hint keys verbatim — is what lets a ``sku`` hint reach
    ``deleteInventoryItem`` and an ``offer_id`` hint reach ``withdrawOffer``
    with no per-operation special casing, and what makes a missing arg visible
    instead of silently sending an empty path segment.
    """
    path_params: dict[str, str] = {}
    for param in operation.path_params:
        value = args.get(param.python_name)
        if value is None:
            value = args.get(param.wire_name)
        if value is None:
            continue
        path_params[param.wire_name] = value
    return path_params


def _resolve_operation(manifest: Any, key: str) -> Any:
    """Resolve a canonical operation key, honouring the contract accessor name.

    The integration contract names ``manifest.operation(key)``; the manifest
    currently exposes ``get(key)`` for canonical-key lookup. Prefer the contract
    name when present so a future accessor rename needs no change here, and fall
    back to ``get`` otherwise. A missing operation is a hard error: executing a
    plan that references an unknown op would silently no-op that step.
    """
    accessor = getattr(manifest, "operation", None)
    record = accessor(key) if callable(accessor) else manifest.get(key)
    if record is None:
        raise LookupError(f"no operation in manifest for revert key {key!r}")
    return record


def execute_plan(context: Any, plan: RevertPlan) -> list[dict[str, Any]]:
    """Run each compensating step in order, stopping at the first failure.

    Every step is re-dispatched through the normal in-process path
    (:func:`bidkit_cli.dispatch.execute`) so compensating calls share the same
    auth, retry, safety-gate, and recording machinery as the original
    invocation. Blocked steps never execute — they exist on the plan only to be
    reported.

    A failing step is recorded with its exception text and aborts the run; later
    steps are not attempted and the partial results collected so far are
    returned. The exception is surfaced in the result entry rather than
    swallowed, so a caller can decide whether to retry or escalate.

    Coupling note (``compensates``): each op record produced while reverting
    must carry ``compensates={"session_id", "seq"}`` so the undo is auditable
    against the original session. ``dispatch.execute`` owns op-record emission,
    so this function hands the link to it through a context attribute,
    ``context._revert_compensates``, that dispatch is expected to forward to
    ``recorder.record_op(..., compensates=context._revert_compensates)``. The
    attribute is set per step and cleared in a ``finally`` so a later,
    non-revert dispatch in the same process can never inherit a stale link.
    """
    results: list[dict[str, Any]] = []
    for step in plan.steps:
        try:
            operation = _resolve_operation(context.manifest, step.operation_key)
            path_params = _path_params_for(operation, step.args)
            # Hand the audit link to dispatch via the context (see coupling note).
            context._revert_compensates = {
                "session_id": plan.session_id,
                "seq": step.source_seq,
            }
            execute(
                context,
                operation,
                path_params=path_params,
                query_params={},
                header_params={},
                body=None,
                files={},
            )
        except Exception as exc:
            results.append({
                "seq": step.source_seq,
                "operation": step.operation_key,
                "status": "failed",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
            break
        else:
            results.append({
                "seq": step.source_seq,
                "operation": step.operation_key,
                "status": "ok",
                "ok": True,
                "error": None,
            })
        finally:
            # Never leave the link set: the same context may outlive this plan.
            context._revert_compensates = None
    return results
