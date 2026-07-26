"""Tests for session revert plan building and execution.

The plan-builder tests are written against hand-authored JSONL session fixtures
and the public reverse table in :mod:`bidkit_cli.session`; they are skipped when
that sibling module is not yet present (the worker that owns it has not landed
it). The execution test stands on its own: it drives ``execute_plan`` with a
fake context and a patched dispatcher, so it exercises the stop-at-first-failure
contract without depending on the recorder or the reverse table at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bidkit_cli.session_revert import RevertPlan, RevertStep, build_plan, execute_plan

# Fixed identifiers keep the fixtures deterministic and the assertions readable.
SID = "01HXZZZZZZZZZZZZZZZZZZZZZ0"
IID = "01HXZZZZZZZZZZZZZZZZZZZZZ1"


# ---------------------------------------------------------------------------
# JSONL fixture helpers
# ---------------------------------------------------------------------------

def _record(record_type: str, seq: int, **fields: object) -> dict[str, object]:
    """One session record with the common keys every line must carry."""
    record: dict[str, object] = {
        "v": 1,
        "type": record_type,
        "ts": "2026-01-01T00:00:00.000Z",
        "session_id": SID,
        "invocation_id": IID,
        "seq": seq,
    }
    record.update(fields)
    return record


def _op(
    seq: int,
    operation_key: str,
    *,
    ids: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
    pre_state: str | None = None,
) -> dict[str, object]:
    """A realistic ``op`` record, carrying only the fields build_plan reads."""
    return _record(
        "op",
        seq,
        operation_id=operation_key,
        classification="write",
        http={"method": "POST", "url": "https://api.ebay.com/x", "status": 200,
              "elapsed_ms_total": 50, "attempts": []},
        ebay={"request_id": "r", "rlogid": "l"},
        request={"params": params or {}, "body": None, "body_ref": None,
                 "body_sha256": None},
        response={"body": None, "body_ref": None, "body_sha256": None},
        ids=ids or {},
        test_run_id=None,
        pre_state=pre_state,
        reverse_hint=None,
        irreversible=False,
        compensates=None,
    )


def _write_session(tmp_path: Path, records: list[dict[str, object]],
                   name: str = "sess.jsonl") -> Path:
    """Write records as one JSON object per line; return the file path."""
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


# ---------------------------------------------------------------------------
# build_plan: reverse-chronological mapping, filtering, classification
# ---------------------------------------------------------------------------

def test_plan_is_reverse_chronological_and_maps_compensating_ops(
    tmp_path: Path,
) -> None:
    """A create+publish session reverses to withdraw then delete, newest first."""
    pytest.importorskip("bidkit_cli.session")
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.createOffer", ids={"offer_id": "O1"}),
        _op(1, "sell_inventory.publishOffer",
            ids={"offer_id": "O1"}, params={"offerId": "O1"}),
    ])
    plan = build_plan(path)

    assert plan.session_id == SID
    assert plan.session_path == path
    # Nothing in this session is blocked.
    assert plan.blocked == []
    # Newest op (publishOffer) maps to withdrawOffer and comes first.
    assert [step.operation_key for step in plan.steps] == [
        "sell_inventory.withdrawOffer",
        "sell_inventory.deleteOffer",
    ]
    assert plan.steps[0].source_seq == 1
    assert plan.steps[0].args == {"offer_id": "O1"}
    assert plan.steps[0].tier == "compensating"
    assert plan.steps[1].source_seq == 0
    assert plan.steps[1].args == {"offer_id": "O1"}


def test_only_last_keeps_the_newest_ops(tmp_path: Path) -> None:
    """only_last=N keeps the N newest ops (already reversed to newest-first)."""
    pytest.importorskip("bidkit_cli.session")
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.createOffer", ids={"offer_id": "O1"}),
        _op(1, "sell_inventory.publishOffer",
            ids={"offer_id": "O1"}, params={"offerId": "O1"}),
    ])
    plan = build_plan(path, only_last=1)
    assert [step.operation_key for step in plan.steps] == ["sell_inventory.withdrawOffer"]
    assert plan.steps[0].source_seq == 1


def test_only_seq_selects_a_single_op(tmp_path: Path) -> None:
    """only_seq=S keeps only the op whose seq equals S."""
    pytest.importorskip("bidkit_cli.session")
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.createOffer", ids={"offer_id": "O1"}),
        _op(1, "sell_inventory.publishOffer",
            ids={"offer_id": "O1"}, params={"offerId": "O1"}),
    ])
    plan = build_plan(path, only_seq=0)
    assert [step.operation_key for step in plan.steps] == ["sell_inventory.deleteOffer"]
    assert plan.steps[0].source_seq == 0


def test_only_last_and_only_seq_are_mutually_exclusive(tmp_path: Path) -> None:
    """Combining the two filters is ambiguous and must be refused.

    This guard runs before the reverse table is consulted, so it holds even
    before session.py exists.
    """
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.createOffer", ids={"offer_id": "O1"}),
    ])
    with pytest.raises(ValueError):
        build_plan(path, only_last=1, only_seq=0)


def test_irreversible_op_is_blocked_with_reason_and_never_in_steps(
    tmp_path: Path,
) -> None:
    """A sell_finances mutation is irreversible: reported, never compensated."""
    pytest.importorskip("bidkit_cli.session")
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.createOffer", ids={"offer_id": "O1"}),
        _op(1, "sell_finances.createFee", ids={"fee_id": "F1"}),
    ])
    plan = build_plan(path)

    # Only the reversible createOffer produces a compensating step.
    assert [step.operation_key for step in plan.steps] == ["sell_inventory.deleteOffer"]
    # The finances mutation is blocked as irreversible, newest-first.
    blocked_finance = next(
        step for step in plan.blocked
        if step.operation_key == "sell_finances.createFee"
    )
    assert blocked_finance.tier == "irreversible"
    assert blocked_finance.source_seq == 1
    assert blocked_finance.note == "a booked fee cannot be reversed by deleting records"
    # And it is never promoted into steps.
    assert all("sell_finances" not in step.operation_key for step in plan.steps)


def test_unknown_op_is_blocked_as_unknown(tmp_path: Path) -> None:
    """An op with no reverse mapping and no prior state is blocked as unknown."""
    pytest.importorskip("bidkit_cli.session")
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.getOffers", params={}),
    ])
    plan = build_plan(path)

    assert plan.steps == []
    assert len(plan.blocked) == 1
    assert plan.blocked[0].operation_key == "sell_inventory.getOffers"
    assert plan.blocked[0].tier == "unknown"
    assert plan.blocked[0].note == "no reverse mapping for this operation"


def test_pre_state_without_reverse_hint_is_restoring(tmp_path: Path) -> None:
    """An op with a recorded prior state and no reverse hint is blocked restoring."""
    pytest.importorskip("bidkit_cli.session")
    path = _write_session(tmp_path, [
        _op(0, "sell_inventory.updateOffer",
            params={"offerId": "O1"}, pre_state="ab/blob.json"),
    ])
    plan = build_plan(path)

    assert plan.steps == []
    assert len(plan.blocked) == 1
    assert plan.blocked[0].tier == "restoring"
    assert plan.blocked[0].note == "restoring a prior state is not automated yet"


# ---------------------------------------------------------------------------
# execute_plan: stop at first failure, partial results, compensates link
# ---------------------------------------------------------------------------

class _FakeParam:
    """Stand-in for ParameterRecord: only python/wire names are read."""

    def __init__(self, python_name: str, wire_name: str) -> None:
        self.python_name = python_name
        self.wire_name = wire_name


class _FakeOp:
    """Stand-in for OperationRecord: only path_params is read."""

    def __init__(self, path_params: list[_FakeParam]) -> None:
        self.path_params = path_params


class _FakeManifest:
    """Resolves by canonical key like the real manifest.operation/get."""

    def __init__(self, ops: dict[str, _FakeOp]) -> None:
        self._ops = ops

    def operation(self, key: str) -> _FakeOp | None:
        return self._ops.get(key)

    def get(self, key: str) -> _FakeOp | None:
        return self._ops.get(key)


class _FakeContext:
    """Minimal context: a manifest plus the attribute dispatch reads back."""

    def __init__(self, manifest: _FakeManifest) -> None:
        self.manifest = manifest
        self._revert_compensates: dict[str, object] | None = None


def test_execute_plan_stops_at_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Execution stops at the first failing step and returns partial results.

    No recorder or reverse table is involved: the dispatcher itself is patched,
    so this pins the stop-on-failure / partial-result / compensates-link
    contract independently of the rest of the session feature.
    """
    plan = RevertPlan(
        session_id=SID,
        session_path=Path("/tmp/ignored.jsonl"),
        steps=[
            RevertStep(source_seq=1, operation_key="sell_inventory.withdrawOffer",
                       args={"offer_id": "O1"}, tier="compensating"),
            RevertStep(source_seq=2, operation_key="sell_inventory.deleteOffer",
                       args={"offer_id": "O2"}, tier="compensating"),
            RevertStep(source_seq=3, operation_key="sell_inventory.deleteInventoryItem",
                       args={"sku": "S3"}, tier="compensating"),
        ],
        blocked=[],
    )
    manifest = _FakeManifest({
        "sell_inventory.withdrawOffer": _FakeOp([_FakeParam("offer_id", "offerId")]),
        "sell_inventory.deleteOffer": _FakeOp([_FakeParam("offer_id", "offerId")]),
        "sell_inventory.deleteInventoryItem": _FakeOp([_FakeParam("sku", "sku")]),
    })
    context = _FakeContext(manifest)

    seen: list[tuple[_FakeOp, dict[str, str], dict[str, object]]] = []

    def fake_execute(
        ctx: _FakeContext,
        operation: _FakeOp,
        *,
        path_params: dict[str, str],
        query_params: dict[str, object],
        header_params: dict[str, str],
        body: object,
        files: dict[str, object],
    ) -> None:
        seen.append((operation, dict(path_params), dict(ctx._revert_compensates or {})))
        if len(seen) == 2:
            raise RuntimeError("second-step failure")

    monkeypatch.setattr("bidkit_cli.session_revert.execute", fake_execute)

    results = execute_plan(context, plan)

    # The third step is never attempted: we stop at the first failure.
    assert len(results) == 2
    assert len(seen) == 2

    assert results[0] == {
        "seq": 1, "operation": "sell_inventory.withdrawOffer",
        "status": "ok", "ok": True, "error": None,
    }
    assert results[1]["ok"] is False
    assert results[1]["status"] == "failed"
    assert results[1]["seq"] == 2
    # The exception text is surfaced, not swallowed.
    assert "second-step failure" in results[1]["error"]

    # Reverse-hint args (python names) were mapped onto path params (wire names).
    assert seen[0][1] == {"offerId": "O1"}
    # The compensates audit link was handed to dispatch through the context.
    assert seen[0][2] == {"session_id": SID, "seq": 1}
    # The link is cleared after the plan so a later dispatch cannot inherit it.
    assert context._revert_compensates is None
