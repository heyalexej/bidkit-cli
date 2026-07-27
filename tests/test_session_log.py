"""Tests for the bidkit-cli session log (``bidkit_cli.session``).

These cover the public contract in CONTRACT.md: base-dir resolution, a full
record cycle, body spilling, file/dir permissions, fail-open behaviour, the
no-secrets guarantee, ULID generation, and the reverse-hint table.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx2
import pytest

from bidkit_cli import session as S
from bidkit_cli.session import (
    SCHEMA_VERSION,
    AttemptCollector,
    NullRecorder,
    SessionRecorder,
    irreversible_reason,
    new_id,
    redact_argv,
    reverse_hint_for,
    sessions_base_dir,
)

TOKEN = "v^1.1#i^1#f^0#r^1#I^3#p^3#t^SECRETTOKEN"


def _base_invocation() -> dict:
    return {
        "argv": ["bidkit", "sell", "inventory", "get"],
        "cwd": "/tmp",
        "env_fingerprint": {"cli_version": "0.2.0"},
        "config_path": None,
        "environment": "production",
        "marketplace_id": "EBAY_DE",
        "test_run_id": None,
        "caller": None,
        "dry_run": False,
        "parent_session_id": None,
    }


def _read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ------------------------------------------------------------------------------------------------
# Base directory resolution
# ------------------------------------------------------------------------------------------------


def test_base_dir_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BIDKIT_SESSIONS_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    # Default fallback when nothing is set.
    assert sessions_base_dir() == Path("~/.local/state/bidkit/sessions").expanduser()

    xdg = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg))
    assert sessions_base_dir() == xdg / "bidkit" / "sessions"

    custom = tmp_path / "custom"
    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(custom))
    assert sessions_base_dir() == custom

    # An explicit override wins over both env vars.
    override = tmp_path / "override"
    assert sessions_base_dir(str(override)) == override


# ------------------------------------------------------------------------------------------------
# Full record cycle
# ------------------------------------------------------------------------------------------------


def test_full_cycle_writes_valid_jsonl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(tmp_path))
    monkeypatch.delenv("BIDKIT_SESSION_STRICT", raising=False)

    rec = SessionRecorder.start(base_dir=tmp_path, invocation=_base_invocation())
    assert rec.enabled
    assert len(rec.session_id) == 26
    assert len(rec.invocation_id) == 26

    rec.record_op(
        operation_id="sell_inventory.createOffer",
        classification="mutation",
        http={
            "method": "POST",
            "url": "https://api.ebay.com/sell/inventory/v1/offer",
            "status": 200,
            "elapsed_ms_total": 42,
            "attempts": [],
        },
        ebay={"request_id": "req-1", "rlogid": "rlog-1"},
        request_params={"sku": "SKU-1"},
        request_body={"sku": "SKU-1", "format": "FIXED_PRICE"},
        response_body={"offerId": "O-1"},
        ids={"offer_id": "O-1"},
        test_run_id=None,
        pre_state=None,
        reverse_hint=reverse_hint_for(
            "sell_inventory.createOffer", ids={"offer_id": "O-1"}, params={}
        ),
        irreversible=False,
        compensates=None,
    )
    rec.finish(0)

    records = _read_records(rec.path)
    assert [r["type"] for r in records] == ["invocation", "op", "end"]
    assert [r["seq"] for r in records] == [0, 1, 2]

    common = {"v", "type", "ts", "session_id", "invocation_id", "seq"}
    for record in records:
        assert common.issubset(record.keys())
        assert record["v"] == SCHEMA_VERSION
        assert record["session_id"] == rec.session_id
        assert record["invocation_id"] == rec.invocation_id
        assert record["ts"].endswith("Z")
        # millisecond precision: exactly 3 digits after the seconds dot.
        assert record["ts"][19] == "."
        assert len(record["ts"][20:23]) == 3

    op = records[1]
    assert op["operation_id"] == "sell_inventory.createOffer"
    assert op["http"]["status"] == 200
    assert op["request"]["params"] == {"sku": "SKU-1"}
    assert op["response"]["body"] == {"offerId": "O-1"}
    assert op["reverse_hint"] == {
        "op": "sell_inventory.deleteOffer",
        "args": {"offer_id": "O-1"},
    }
    assert records[2]["exit_code"] == 0
    assert records[2]["duration_ms"] >= 0


# ------------------------------------------------------------------------------------------------
# Body spilling
# ------------------------------------------------------------------------------------------------


def _start_rec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionRecorder:
    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(tmp_path))
    return SessionRecorder.start(base_dir=tmp_path, invocation=_base_invocation())


def test_small_body_stays_inline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rec = _start_rec(tmp_path, monkeypatch)
    small = {"sku": "S", "note": "hello"}
    rec.record_op(
        operation_id="x", classification="read",
        http={"method": "GET", "url": "u", "status": 200,
              "elapsed_ms_total": 1, "attempts": []},
        ebay={"request_id": None, "rlogid": None},
        request_body=small, response_body=small, ids={},
    )
    rec.finish(0)
    op = _read_records(rec.path)[1]
    assert op["request"]["body"] == small
    assert op["request"]["body_ref"] is None
    assert len(op["request"]["body_sha256"]) == 64
    assert op["response"]["body"] == small
    assert op["response"]["body_ref"] is None


def test_large_body_spills_to_blob(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rec = _start_rec(tmp_path, monkeypatch)
    big = {"blob": "x" * 4000}
    rec.record_op(
        operation_id="x", classification="read",
        http={"method": "GET", "url": "u", "status": 200,
              "elapsed_ms_total": 1, "attempts": []},
        ebay={"request_id": None, "rlogid": None},
        request_body=big, response_body=big, ids={},
    )
    rec.finish(0)
    op = _read_records(rec.path)[1]

    for side in ("request", "response"):
        body_record = op[side]
        assert body_record["body"] is None
        assert body_record["body_ref"] is not None
        assert len(body_record["body_sha256"]) == 64

        blob = Path(body_record["body_ref"])
        assert blob.exists(), f"blob for {side} should exist"
        # Layout: <base>/bodies/<first2 of sha>/<sha>.json
        assert blob.relative_to(tmp_path).parts[0] == "bodies"
        assert blob.parent.name == body_record["body_sha256"][:2]
        assert blob.name == f"{body_record['body_sha256']}.json"
        # The sha matches the blob's bytes.
        import hashlib

        assert hashlib.sha256(blob.read_bytes()).hexdigest() == body_record["body_sha256"]


def test_binary_body_hashed_not_serialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rec = _start_rec(tmp_path, monkeypatch)
    payload = b"\x00\x01\xff" * 1000
    rec.record_op(
        operation_id="commerce_media.uploadVideo", classification="unknown",
        http={"method": "POST", "url": "u", "status": 200,
              "elapsed_ms_total": 1, "attempts": []},
        ebay={"request_id": None, "rlogid": None},
        request_body=payload, response_body=None, ids={},
    )
    rec.finish(0)

    # The recorder must survive a binary body: op AND end records exist.
    assert rec.enabled
    records = _read_records(rec.path)
    assert [r["type"] for r in records] == ["invocation", "op", "end"]

    op = records[1]
    assert op["request"]["body"] == {"binary": True, "size": len(payload)}
    assert op["request"]["body_ref"] is None
    import hashlib

    assert op["request"]["body_sha256"] == hashlib.sha256(payload).hexdigest()
    # The raw bytes are hashed, never spilled to the blob store.
    assert not (tmp_path / "bodies").exists()


# ------------------------------------------------------------------------------------------------
# Permissions
# ------------------------------------------------------------------------------------------------


def test_file_and_dir_permissions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rec = _start_rec(tmp_path, monkeypatch)
    rec.finish(0)

    file_mode = stat.S_IMODE(os.stat(rec.path).st_mode)
    assert file_mode == 0o600
    dir_mode = stat.S_IMODE(os.stat(rec.path.parent).st_mode)
    assert dir_mode == 0o700


def test_blob_dir_permissions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rec = _start_rec(tmp_path, monkeypatch)
    rec.record_op(
        operation_id="x", classification="read",
        http={"method": "GET", "url": "u", "status": 200,
              "elapsed_ms_total": 1, "attempts": []},
        ebay={"request_id": None, "rlogid": None},
        request_body={"blob": "x" * 4000}, response_body=None, ids={},
    )
    rec.finish(0)
    op = _read_records(rec.path)[1]
    blob = Path(op["request"]["body_ref"])
    assert stat.S_IMODE(os.stat(blob).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(blob.parent).st_mode) == 0o700


# ------------------------------------------------------------------------------------------------
# Fail-open
# ------------------------------------------------------------------------------------------------


def _invocation_record_op_finish(rec: SessionRecorder) -> None:
    rec.record_op(
        operation_id="x", classification="read",
        http={"method": "GET", "url": "u", "status": 200,
              "elapsed_ms_total": 1, "attempts": []},
        ebay={"request_id": None, "rlogid": None},
        request_body={"a": 1}, response_body={"b": 2}, ids={},
    )
    rec.finish(0)


def test_fail_open_warns_once_and_disables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv("BIDKIT_SESSION_STRICT", raising=False)
    base = tmp_path / "sessions"
    base.mkdir()
    base.chmod(0o000)
    try:
        rec = SessionRecorder.start(base_dir=base, invocation=_base_invocation())
        _invocation_record_op_finish(rec)
        assert rec.enabled is False
    finally:
        base.chmod(0o700)  # restore so tmp_path cleanup can proceed

    err = capsys.readouterr().err
    assert err.count("warning: session log unavailable") == 1


def test_strict_mode_reraises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BIDKIT_SESSION_STRICT", "1")
    base = tmp_path / "sessions"
    base.mkdir()
    base.chmod(0o000)
    try:
        with pytest.raises(OSError):
            SessionRecorder.start(base_dir=base, invocation=_base_invocation())
    finally:
        base.chmod(0o700)


def test_fail_open_after_successful_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    # Start succeeds, then the session dir becomes unwritable: subsequent writes
    # must fail open too.
    monkeypatch.delenv("BIDKIT_SESSION_STRICT", raising=False)
    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(tmp_path))
    rec = SessionRecorder.start(base_dir=tmp_path, invocation=_base_invocation())
    assert rec.enabled

    rec.path.parent.chmod(0o000)
    try:
        # No exception, recorder disables itself.
        _invocation_record_op_finish(rec)
        assert rec.enabled is False
    finally:
        rec.path.parent.chmod(0o700)

    err = capsys.readouterr().err
    assert err.count("warning: session log unavailable") == 1


# ------------------------------------------------------------------------------------------------
# No secrets
# ------------------------------------------------------------------------------------------------


def test_no_secrets_anywhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BIDKIT_SESSIONS_DIR", str(tmp_path))
    invocation = _base_invocation()
    # Token passed as the value of a sensitive flag AND as a positional arg.
    invocation["argv"] = ["bidkit", "--token", TOKEN, "sell", TOKEN, "stuff"]

    rec = SessionRecorder.start(base_dir=tmp_path, invocation=invocation)
    rec.record_op(
        operation_id="x", classification="read",
        http={"method": "GET", "url": "u", "status": 200,
              "elapsed_ms_total": 1, "attempts": []},
        ebay={"request_id": None, "rlogid": None},
        request_body={
            "access_token": TOKEN,
            "authorization": f"Bearer {TOKEN}",
            "sku": "ABC",
            "note": TOKEN,  # token-shaped value under a benign key
        },
        response_body={"authorization": TOKEN, "ok": True},
        ids={},
    )
    rec.finish(0)

    content = rec.path.read_text()
    assert TOKEN not in content
    assert "SECRETTOKEN" not in content

    # Check every spilled blob too.
    for record in _read_records(rec.path):
        if record.get("type") != "op":
            continue
        for side in ("request", "response"):
            body_ref = record[side].get("body_ref")
            if body_ref:
                blob_text = Path(body_ref).read_text()
                assert TOKEN not in blob_text
                assert "SECRETTOKEN" not in blob_text


def test_redact_argv_masks_token_flags_and_values() -> None:
    masked = redact_argv(
        ["bidkit", "--token", TOKEN, "--api-key=" + TOKEN, "call", TOKEN, "--ok", "fine"]
    )
    # Token value never survives in any position.
    assert TOKEN not in masked
    assert "SECRETTOKEN" not in "".join(masked)
    # Sensitive flag value replaced.
    assert "--token" in masked
    token_idx = masked.index("--token")
    assert masked[token_idx + 1] == "<redacted>"
    # --api-key= form replaced inline.
    assert "--api-key=<redacted>" in masked
    # Benign flag/value preserved.
    ok_idx = masked.index("--ok")
    assert masked[ok_idx + 1] == "fine"


# ------------------------------------------------------------------------------------------------
# new_id
# ------------------------------------------------------------------------------------------------


def test_new_id_shape_and_monotonicity() -> None:
    ids = [new_id() for _ in range(20)]
    assert all(len(i) == 26 for i in ids)
    assert all(c in S._CROCKFORD for i in ids for c in i)
    # Lexicographically increasing across rapid consecutive calls.
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


# ------------------------------------------------------------------------------------------------
# Reverse hints
# ------------------------------------------------------------------------------------------------


def test_reverse_hint_for_documented_ops() -> None:
    assert reverse_hint_for(
        "sell_inventory.createOffer", ids={"offer_id": "O1"}, params={}
    ) == {"op": "sell_inventory.deleteOffer", "args": {"offer_id": "O1"}}
    assert reverse_hint_for(
        "sell_inventory.publishOffer", ids={"offer_id": "O1"}, params={}
    ) == {"op": "sell_inventory.withdrawOffer", "args": {"offer_id": "O1"}}
    assert reverse_hint_for(
        "sell_inventory.createOrReplaceInventoryItem", ids={"sku": "S1"}, params={}
    ) == {"op": "sell_inventory.deleteInventoryItem", "args": {"sku": "S1"}}


def test_reverse_hint_for_unknown_and_missing_args() -> None:
    assert reverse_hint_for("sell_inventory.getOffer", ids={}, params={}) is None
    assert reverse_hint_for("totally.unknown", ids={}, params={}) is None
    # Missing the required arg -> None (cannot build a half hint).
    assert reverse_hint_for("sell_inventory.createOffer", ids={}, params={}) is None


def test_reverse_hint_arg_falls_back_to_params() -> None:
    assert reverse_hint_for(
        "sell_inventory.createOrReplaceInventoryItem", ids={}, params={"sku": "S9"}
    ) == {"op": "sell_inventory.deleteInventoryItem", "args": {"sku": "S9"}}


def test_irreversible_reasons() -> None:
    assert irreversible_reason("sell_inventory.bulkPublishOffer") == (
        "bulk publish must be withdrawn per offer"
    )
    assert irreversible_reason("sell_finances.someMutation").startswith(
        "a booked fee cannot be reversed"
    )
    assert irreversible_reason("commerce_message.sendMessage").startswith(
        "a sent message cannot be unsent"
    )
    assert irreversible_reason("sell_feedback.leaveFeedback").startswith(
        "left feedback cannot be withdrawn"
    )
    assert irreversible_reason("sell_inventory.getOffer") is None


# ------------------------------------------------------------------------------------------------
# AttemptCollector (httpx2 hooks)
# ------------------------------------------------------------------------------------------------


def test_attempt_collector_captures_request_and_response() -> None:
    coll = AttemptCollector()
    request = httpx2.Request("POST", "https://api.ebay.com/sell/inventory/v1/offer")
    coll.request_hook(request)
    response = httpx2.Response(
        200, request=request, headers={"x-ebay-c-request-id": "rid-42"}
    )
    coll.response_hook(response)

    attempts = coll.drain()
    assert len(attempts) == 1
    entry = attempts[0]
    assert entry["n"] == 1
    assert entry["status"] == 200
    assert entry["ebay_request_id"] == "rid-42"
    assert entry["error"] is None
    assert entry["elapsed_ms"] >= 0
    # Draining clears the collector.
    assert coll.drain() == []


def test_attempt_collector_counts_multiple_attempts() -> None:
    coll = AttemptCollector()
    for _ in range(3):
        request = httpx2.Request("GET", "https://api.ebay.com/x")
        coll.request_hook(request)
        response = httpx2.Response(500, request=request)
        coll.response_hook(response)
    attempts = coll.drain()
    assert [a["n"] for a in attempts] == [1, 2, 3]
    assert all(a["status"] == 500 for a in attempts)


def test_attempt_collector_records_transport_error() -> None:
    coll = AttemptCollector()
    request = httpx2.Request("POST", "https://api.ebay.com/x")
    coll.request_hook(request)
    coll.note_transport_error(ConnectionError("reset by peer"))
    attempts = coll.drain()
    assert len(attempts) == 1
    assert attempts[0]["status"] is None
    assert "reset by peer" in attempts[0]["error"]


# ------------------------------------------------------------------------------------------------
# NullRecorder
# ------------------------------------------------------------------------------------------------


def test_null_recorder_is_silent(tmp_path: Path) -> None:
    rec = NullRecorder.start(invocation=_base_invocation())
    assert rec.enabled is False
    rec.record_op(operation_id="x", classification="read", http={}, ebay={}, ids={})
    rec.finish(0)
    # No file was ever created.
    assert rec.path == Path()
