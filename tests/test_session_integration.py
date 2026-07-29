"""Wire-level integration of the session recorder into dispatch (CONTRACT §Integration).

These tests drive :func:`bidkit_cli.dispatch.execute` over an ``httpx2.MockTransport``
(in the style of ``tests/test_dispatch.py``) and assert the session log records
land on disk — while ``--no-session-log`` writes nothing, a failed dispatch
writes an ``error`` record, and a recorder that raises internally can never
break the command (the audit log is strictly best-effort, like the run ledger).
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import TypeGuard

import httpx2
import orjson
import pytest
from bidkit import EbayClient, EbayConfig

from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import ApiError
from bidkit_cli.manifest import Manifest

# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def _session_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.jsonl"))


def _records(path: Path) -> list[dict[str, object]]:
    return [orjson.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _is_record(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _ctx_with_session(
    manifest: Manifest,
    handler,
    sessions_dir: Path,
    *,
    session_log: bool = True,
    **ctx_kwargs,
) -> CliContext:
    """A CliContext whose injected mock client shares the recorder's collector.

    Mirrors what :pyattr:`CliContext.client` builds (an httpx2 client carrying
    the recorder's AttemptCollector hooks) but over a MockTransport, so the
    captured attempts array is non-empty and no real network is hit.
    """
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._config = EbayConfig(access_token="t")
    ctx.output_format = "json"
    ctx.pretty = False
    ctx.session_log = session_log
    ctx.sessions_dir = str(sessions_dir)
    for key, value in ctx_kwargs.items():
        setattr(ctx, key, value)
    # Build the client by hand so the mock transport AND the recorder's
    # collector hooks ride the same httpx2 client (exactly as context.client
    # does for a real transport).
    collector = ctx.recorder.attempts()
    http = httpx2.Client(
        transport=httpx2.MockTransport(handler),
        event_hooks={
            "request": [collector.request_hook],
            "response": [collector.response_hook],
        },
    )
    ctx._http = http
    ctx._client = EbayClient(ctx._config, http_client=http)
    return ctx


def _run(ctx: CliContext, op, **call_kwargs) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, **call_kwargs)
    return buf.getvalue()


class _RaisingRecorder:
    """A recorder whose record methods always blow up, to prove fail-open."""

    def attempts(self):
        from bidkit_cli.session import AttemptCollector

        return AttemptCollector()

    def record_gate(self, **fields) -> None:
        raise RuntimeError("recorder explosion")

    def record_op(self, **fields) -> None:
        raise RuntimeError("recorder explosion")

    def record_error(self, **fields) -> None:
        raise RuntimeError("recorder explosion")

    def finish(self, exit_code: int) -> None:
        raise RuntimeError("recorder explosion")


# ---------------------------------------------------------------------------
# op record on a successful dispatch
# ---------------------------------------------------------------------------


def test_dispatched_read_writes_op_with_attempts(
    manifest: Manifest, tmp_path: Path
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"x-ebay-c-request-id": "req-1"},
            json={"sku": "A", "title": "t"},
        )

    ctx = _ctx_with_session(manifest, handler, tmp_path)
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None
    _run(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
         body=None, files={})

    files = _session_files(tmp_path)
    assert len(files) == 1
    records = _records(files[0])
    types = [r["type"] for r in records]
    assert "invocation" in types
    assert "gate" in types
    assert "op" in types
    op_rec = next(r for r in records if r["type"] == "op")
    assert op_rec["operation_id"] == op.key
    # The collector observed the single mock attempt.
    http = op_rec["http"]
    assert _is_record(http)
    attempts = http["attempts"]
    assert _is_object_list(attempts)
    assert len(attempts) == 1
    first_attempt = attempts[0]
    assert _is_record(first_attempt)
    assert first_attempt["status"] == 200
    assert http["status"] == 200
    ebay = op_rec["ebay"]
    assert _is_record(ebay)
    assert ebay["request_id"] == "req-1"
    ctx.close()


def test_dispatched_write_records_reverse_hint(
    manifest: Manifest, tmp_path: Path
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        # --merge GETs first (404 -> pass-through), then PUTs.
        if request.method == "GET":
            return httpx2.Response(404, json={"errors": []})
        return httpx2.Response(204)

    ctx = _ctx_with_session(
        manifest, handler, tmp_path, allow_write=True, yes=True, merge=True
    )
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    _run(ctx, op, path_params={"sku": "SKU-X"}, query_params={}, header_params={},
         body={"product": {"title": "New"}}, files={})

    records = _records(_session_files(tmp_path)[0])
    op_rec = next(r for r in records if r["type"] == "op")
    # A replace-like inventory write is reversible via deleteInventoryItem(sku).
    assert op_rec["reverse_hint"] == {
        "op": "sell_inventory.deleteInventoryItem",
        "args": {"sku": "SKU-X"},
    }
    assert op_rec["irreversible"] is False
    ids = op_rec["ids"]
    assert _is_record(ids)
    assert ids["sku"] == "SKU-X"
    ctx.close()


# ---------------------------------------------------------------------------
# --no-session-log writes nothing
# ---------------------------------------------------------------------------


def test_no_session_log_writes_nothing(manifest: Manifest, tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sku": "A"})

    ctx = _ctx_with_session(manifest, handler, tmp_path, session_log=False)
    assert ctx.recorder.enabled is False
    op = manifest.get("sell_inventory.getInventoryItem")
    _run(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
         body=None, files={})

    assert _session_files(tmp_path) == []
    ctx.close()


# ---------------------------------------------------------------------------
# error record on a classified failure
# ---------------------------------------------------------------------------


def test_failing_dispatch_writes_error_record(
    manifest: Manifest, tmp_path: Path
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            422, headers={"x-ebay-c-request-id": "req-9"},
            json={"errors": [{"message": "bad value"}]},
        )

    ctx = _ctx_with_session(manifest, handler, tmp_path)
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None
    with pytest.raises(ApiError):
        _run(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
             body=None, files={})

    records = _records(_session_files(tmp_path)[0])
    err_rec = next(r for r in records if r["type"] == "error")
    assert err_rec["operation_id"] == op.key
    assert err_rec["status"] == 422
    assert err_rec["request_id"] == "req-9"
    http = err_rec["http"]
    assert _is_record(http)
    assert _is_object_list(http["attempts"])
    ctx.close()


# ---------------------------------------------------------------------------
# a raising recorder never breaks the command
# ---------------------------------------------------------------------------


def test_raising_recorder_does_not_break_command(
    manifest: Manifest, tmp_path: Path
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sku": "A", "title": "t"})

    ctx = CliContext()
    ctx._manifest = manifest
    ctx._config = EbayConfig(access_token="t")
    ctx.output_format = "json"
    ctx.pretty = False
    # Pre-seed a recorder that throws on every record call; the dispatch
    # integration must swallow that and still complete the read.
    ctx._recorder = _RaisingRecorder()
    ctx._client = EbayClient(
        ctx._config, http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    op = manifest.get("sell_inventory.getInventoryItem")
    out = _run(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
               body=None, files={})
    # The command succeeded and rendered its JSON payload despite the recorder.
    payload = json.loads(out)
    assert payload["sku"] == "A"
    ctx.close()


# ---------------------------------------------------------------------------
# Seam regressions: the pieces agreeing on what crosses between them
# ---------------------------------------------------------------------------


def test_records_carry_the_canonical_operation_key(
    manifest: Manifest, tmp_path: Path
) -> None:
    """``operation_id`` must be the manifest key, not the bare method name.

    The revert planner resolves operations by manifest key, so recording
    ``getInventoryItem`` instead of ``sell_inventory.getInventoryItem`` leaves
    every reverse lookup — and therefore every revert plan — silently empty.
    """
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sku": "A"})

    ctx = _ctx_with_session(manifest, handler, tmp_path)
    op = manifest.get("sell_inventory.getInventoryItem")
    _run(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
         body=None, files={})

    records = _records(_session_files(tmp_path)[0])
    keyed = [r for r in records if r["type"] in {"gate", "op"}]
    assert keyed, "expected gate + op records"
    for record in keyed:
        assert record["operation_id"] == "sell_inventory.getInventoryItem"
    ctx.close()


def test_recorded_write_round_trips_into_a_revert_plan(
    manifest: Manifest, tmp_path: Path
) -> None:
    """A create recorded by dispatch must plan back to its compensating call.

    Recorder and planner each pass their own unit tests against their own
    fixtures; only a round trip proves they agree on the record shape.
    """
    from bidkit_cli.session_revert import build_plan

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            return httpx2.Response(404, json={"errors": []})
        return httpx2.Response(204)

    ctx = _ctx_with_session(
        manifest, handler, tmp_path, allow_write=True, yes=True, merge=True
    )
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    _run(ctx, op, path_params={"sku": "ABABABABAB"}, query_params={}, header_params={},
         body={"product": {"title": "t"}}, files={})
    ctx.close()

    plan = build_plan(_session_files(tmp_path)[0])
    assert [step.operation_key for step in plan.steps] == [
        "sell_inventory.deleteInventoryItem"
    ]
    assert plan.steps[0].args == {"sku": "ABABABABAB"}


def test_inspecting_sessions_does_not_create_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading the log must not extend it.

    If ``session list`` logged itself, the count would change every time it ran
    and ``doctor``/``prune`` would inflate the very thing they audit.
    """
    from click.testing import CliRunner

    from bidkit_cli import app as app_module

    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(tmp_path))
    runner = CliRunner()
    cli = app_module.build_cli()
    for _ in range(3):
        result = runner.invoke(cli, ["session", "list", "--format", "json"])
        assert result.exit_code == 0, result.output

    assert _session_files(tmp_path) == [], "inspection must leave no session files"


def test_cli_entrypoint_writes_the_end_record(
    manifest: Manifest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``main`` must close the session, not just the client.

    Click's context stack is unwound before ``main``'s cleanup runs, so reading
    the context back from Click there finds nothing and every clean run would
    look like a crashed session to ``session doctor``.
    """
    from click.testing import CliRunner

    from bidkit_cli import app as app_module

    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app_module.build_cli(), ["api", "list", "--service", "sell_account"])
    assert result.exit_code == 0, result.output

    app_module._finish_and_close(result.exit_code)
    files = _session_files(tmp_path)
    assert files, "the invocation must have opened a session file"
    records = _records(files[0])
    assert records[0]["type"] == "invocation"
    assert records[-1]["type"] == "end"
    assert records[-1]["exit_code"] == 0
    assert isinstance(records[-1]["duration_ms"], int)
