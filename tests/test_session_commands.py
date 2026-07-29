"""Tests for the ``bidkit session`` command group.

These tests do NOT depend on the recorder implementation
(:mod:`bidkit_cli.session`): they hand-write JSONL fixture lines into a tmp
sessions dir and drive ``session_group`` via click's ``CliRunner``, asserting
only against the documented on-disk format (CONTRACT v1).

The ``revert`` execute path additionally needs :mod:`bidkit_cli.session_revert`
(worker D); tests that unavoidably require it use ``importorskip`` so the suite
stays collectible (and green) before that module lands.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson
import pytest
from click.testing import CliRunner, Result

from bidkit_cli.commands.session import session_group
from bidkit_cli.context import CliContext

# ---------------------------------------------------------------------------
# shared harness
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _ctx(
    sessions_dir: Path,
    *,
    allow_write: bool = False,
    yes: bool = False,
    dry_run: bool = False,
) -> CliContext:
    """A CliContext pinned to a tmp sessions dir and JSON output."""
    ctx = CliContext()
    # sessions_dir is added to CliContext by worker C (CONTRACT "Integration");
    # the command reads it via getattr, so setting it on the instance works even
    # before that field is declared.
    ctx.sessions_dir = str(sessions_dir)  # type: ignore[attr-defined]
    ctx.output_format = "json"
    ctx.pretty = False
    ctx.allow_write = allow_write
    ctx.yes = yes
    ctx.dry_run = dry_run
    return ctx


def _rec(
    seq: int,
    type_: str,
    *,
    session_id: str = "01J00000000000000000000001",
    invocation_id: str = "01J00000000000000000000002",
    **extra: object,
) -> dict[str, object]:
    rec: dict[str, object] = {
        "v": 1,
        "type": type_,
        "ts": "2026-01-01T00:00:00.000Z",
        "session_id": session_id,
        "invocation_id": invocation_id,
        "seq": seq,
    }
    rec.update(extra)
    return rec


def _write_session(
    base: Path,
    *,
    session_id: str,
    stamp: str,
    records: list[dict[str, object]],
) -> Path:
    """Write a session JSONL file at <base>/<YYYY-MM>/<stamp>_<session_id>.jsonl."""
    month = stamp[:6]  # YYYYMM
    folder = base / month
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}_{session_id}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for rec in records:
            # Every record in a session file shares that session's id; stamp it
            # here so fixtures stay consistent with the filename by construction.
            rec = {**rec, "session_id": session_id}
            handle.write(orjson.dumps(rec).decode() + "\n")
    return path


def _write_blob(base: Path, sha: str, payload: dict[str, object]) -> Path:
    """Write a spilled body blob at <base>/bodies/<sha[:2]>/<sha>.json."""
    folder = base / "bodies" / sha[:2]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha}.json"
    path.write_text(orjson.dumps(payload).decode(), encoding="utf-8")
    return path


def _out(result: Result) -> dict:
    """Parse the command's JSON stdout, surfacing failures clearly."""
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_shows_sessions_newest_first(runner: CliRunner, tmp_path: Path) -> None:
    _write_session(
        tmp_path,
        session_id="01J00000000000000000000001",
        stamp="20260101T120000Z",
        records=[
            _rec(
                0,
                "invocation",
                session_id="01J00000000000000000000001",
                environment="production",
                marketplace_id="EBAY_DE",
                argv=["bidkit", "sell", "inventory", "get-inventory-items"],
            ),
            _rec(1, "op", operation_id="getInventoryItem"),
            _rec(2, "end", exit_code=0),
        ],
    )
    _write_session(
        tmp_path,
        session_id="01J00000000000000000000002",
        stamp="20260102T090000Z",
        records=[
            _rec(
                0,
                "invocation",
                session_id="01J00000000000000000000002",
                environment="sandbox",
                marketplace_id="EBAY_US",
            ),
            _rec(1, "end", exit_code=1),
        ],
    )

    data = _out(runner.invoke(session_group, ["list"], obj=_ctx(tmp_path)))
    assert data["count"] == 2
    first, second = data["sessions"]
    # Newest-first: the 2026-01-02 session sorts above the 2026-01-01 session.
    assert first["session_id"] == "01J00000000000000000000002"
    assert second["session_id"] == "01J00000000000000000000001"
    assert second["invocations"] == 1
    assert second["ops"] == 1
    assert second["environment"] == "production"
    assert second["marketplace"] == "EBAY_DE"
    assert second["exit_codes"] == [0]


def test_list_since_and_limit(runner: CliRunner, tmp_path: Path) -> None:
    now = datetime.now(UTC)
    new_stamp = (now - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
    old_stamp = (now - timedelta(days=40)).strftime("%Y%m%dT%H%M%SZ")
    _write_session(
        tmp_path, session_id="01J0NEW000000000000000000", stamp=new_stamp,
        records=[_rec(0, "invocation"), _rec(1, "end", exit_code=0)],
    )
    _write_session(
        tmp_path, session_id="01J0OLD000000000000000000", stamp=old_stamp,
        records=[_rec(0, "invocation"), _rec(1, "end", exit_code=0)],
    )

    data = _out(runner.invoke(
        session_group, ["list", "--since", "30"], obj=_ctx(tmp_path),
    ))
    assert data["count"] == 1
    assert data["sessions"][0]["session_id"] == "01J0NEW000000000000000000"

    data = _out(runner.invoke(
        session_group, ["list", "--limit", "1"], obj=_ctx(tmp_path),
    ))
    assert data["count"] == 1


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def test_show_records_in_order_and_ops_only(runner: CliRunner, tmp_path: Path) -> None:
    path = _write_session(
        tmp_path,
        session_id="01JSHOW000000000000000000",
        stamp="20260101T120000Z",
        records=[
            _rec(0, "invocation", environment="production",
                 marketplace_id="EBAY_DE"),
            _rec(1, "gate", operation_id="createOffer",
                 allow_write=True, yes=True),
            _rec(2, "op", operation_id="createOffer"),
            _rec(3, "end", exit_code=0),
        ],
    )

    data = _out(runner.invoke(
        session_group, ["show", "01JSHOW000000000000000000"], obj=_ctx(tmp_path),
    ))
    assert [r["type"] for r in data["records"]] == [
        "invocation", "gate", "op", "end",
    ]
    assert data["session_id"] == "01JSHOW000000000000000000"

    # --ops-only restricts to op records; a bare path also resolves the session.
    data = _out(runner.invoke(
        session_group, ["show", str(path), "--ops-only"], obj=_ctx(tmp_path),
    ))
    assert [r["type"] for r in data["records"]] == ["op"]


def test_show_unknown_session_is_usage_error(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        session_group, ["show", "01JMISSING000000000000000"], obj=_ctx(tmp_path),
    )
    assert result.exit_code != 0
    assert "no session" in (result.output + str(result.exception)).lower()


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------

def test_grep_match_and_no_match(runner: CliRunner, tmp_path: Path) -> None:
    _write_session(
        tmp_path,
        session_id="01JGREP000000000000000000",
        stamp="20260101T120000Z",
        records=[
            _rec(0, "invocation"),
            _rec(1, "op", operation_id="createOffer"),
            _rec(2, "op", operation_id="publishOffer"),
            _rec(3, "end", exit_code=0),
        ],
    )

    data = _out(runner.invoke(
        session_group, ["grep", "Offer"], obj=_ctx(tmp_path),
    ))
    # Only the two op records carry "Offer"; the invocation/end lines do not.
    assert data["count"] == 2
    joined = " ".join(m["match"] for m in data["matches"])
    assert "createOffer" in joined
    assert "publishOffer" in joined
    for match in data["matches"]:
        assert match["session_id"] == "01JGREP000000000000000000"
        assert match["type"] == "op"

    data = _out(runner.invoke(
        session_group, ["grep", "ZZZNOMATCHZZZ"], obj=_ctx(tmp_path),
    ))
    assert data["count"] == 0


def test_grep_bad_regex_is_usage_error(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        session_group, ["grep", "("], obj=_ctx(tmp_path),
    )
    assert result.exit_code != 0
    assert "regex" in (result.output + str(result.exception)).lower()


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def test_doctor_detects_missing_end_and_corrupt_line(
    runner: CliRunner, tmp_path: Path,
) -> None:
    # Crashed: an invocation whose last record is an op (no `end`).
    _write_session(
        tmp_path, session_id="01JCRASH00000000000000000", stamp="20260101T120000Z",
        records=[_rec(0, "invocation"), _rec(1, "op", operation_id="createOffer")],
    )
    # Healthy: ends cleanly.
    _write_session(
        tmp_path, session_id="01JOK0000000000000000000", stamp="20260102T120000Z",
        records=[_rec(0, "invocation"), _rec(1, "end", exit_code=0)],
    )
    # Corrupt: one unparseable line mixed into an otherwise-valid file.
    bad = tmp_path / "202601" / "20260103T120000Z_01JBAD000000000000000000.jsonl"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(
        orjson.dumps(_rec(0, "invocation")).decode() + "\nthis is not json\n",
        encoding="utf-8",
    )

    data = _out(runner.invoke(session_group, ["doctor"], obj=_ctx(tmp_path)))
    crashed_ids = {c["session_id"] for c in data["crashed_invocations"]}
    assert "01JCRASH00000000000000000" in crashed_ids
    assert "01JOK0000000000000000000" not in crashed_ids
    assert any("corrupt line" in line for line in data["corrupt_lines"])


def test_doctor_reports_orphaned_blob(runner: CliRunner, tmp_path: Path) -> None:
    _write_blob(tmp_path, "d" * 64, {"unreferenced": True})
    _write_session(
        tmp_path, session_id="01JOK2000000000000000000", stamp="20260101T120000Z",
        records=[_rec(0, "invocation"), _rec(1, "end", exit_code=0)],
    )
    data = _out(runner.invoke(session_group, ["doctor"], obj=_ctx(tmp_path)))
    assert any("d" * 64 in blob for blob in data["orphaned_blobs"])


# ---------------------------------------------------------------------------
# prune
#
# The session log is a durable record, so these tests are mostly about what
# prune REFUSES to do: nothing expires on its own, and history only goes when
# it is asked for explicitly.
# ---------------------------------------------------------------------------

def _aged_session(tmp_path: Path, session_id: str, days: int, sha: str | None = None):
    stamp = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y%m%dT%H%M%SZ")
    records = [_rec(0, "invocation")]
    if sha:
        records.append(_rec(1, "op", operation_id="sell_inventory.createOffer",
                            request={"body_ref": sha, "body_sha256": sha}))
    records.append(_rec(len(records), "end", exit_code=0))
    return _write_session(tmp_path, session_id=session_id, stamp=stamp, records=records)


def test_prune_without_a_selection_removes_nothing(
    runner: CliRunner, tmp_path: Path,
) -> None:
    """Run bare, prune must select nothing: there is no retention policy."""
    session = _aged_session(tmp_path, "01JBAREPRUNE00000000000A", days=900)
    result = runner.invoke(session_group, ["prune"], obj=_ctx(tmp_path, yes=True))
    assert result.exit_code != 0
    assert session.exists()


def test_prune_previews_without_yes(runner: CliRunner, tmp_path: Path) -> None:
    sha = "a" * 64
    session = _aged_session(tmp_path, "01JPREVIEW0000000000000A", days=900, sha=sha)
    blob = _write_blob(tmp_path, sha, {"payload": True})

    data = _out(runner.invoke(
        session_group, ["prune", "--older-than", "30d", "--keep-last", "0"],
        obj=_ctx(tmp_path),
    ))
    assert data["applied"] is False
    assert data["selected_sessions"] == 1
    assert session.exists() and blob.exists(), "a preview must touch nothing"


def test_prune_bodies_keeps_the_record(runner: CliRunner, tmp_path: Path) -> None:
    """Default scope drops payloads while the history stays readable."""
    sha = "a" * 64
    session = _aged_session(tmp_path, "01JBODIES00000000000000A", days=900, sha=sha)
    blob = _write_blob(tmp_path, sha, {"payload": True})

    data = _out(runner.invoke(
        session_group, ["prune", "--older-than", "30d", "--keep-last", "0"],
        obj=_ctx(tmp_path, yes=True),
    ))
    assert data["applied"] is True
    assert data["scope"] == "bodies"
    assert str(blob) in data["removed_blobs"]
    assert not blob.exists()
    # The session — and the digest proving what the body was — survives.
    assert session.exists()
    assert sha in session.read_text()


def test_prune_keeps_blobs_another_session_still_references(
    runner: CliRunner, tmp_path: Path,
) -> None:
    """Blobs are content-addressed and shared; the last referent frees them."""
    sha = "a" * 64
    _aged_session(tmp_path, "01JSHAREDOLD000000000000", days=900, sha=sha)
    _aged_session(tmp_path, "01JSHAREDNEW000000000000", days=1, sha=sha)
    blob = _write_blob(tmp_path, sha, {"payload": True})

    runner.invoke(
        session_group, ["prune", "--older-than", "30d", "--keep-last", "0", "--records"],
        obj=_ctx(tmp_path, yes=True),
    )
    assert blob.exists(), "the recent session still points at this blob"


def test_prune_records_requires_an_explicit_range(
    runner: CliRunner, tmp_path: Path,
) -> None:
    session = _aged_session(tmp_path, "01JNORANGE0000000000000A", days=900)
    result = runner.invoke(
        session_group, ["prune", "--orphans", "--records"], obj=_ctx(tmp_path, yes=True),
    )
    assert result.exit_code != 0
    assert session.exists()


def test_prune_refuses_a_zero_length_range(runner: CliRunner, tmp_path: Path) -> None:
    """`--older-than 0d` means "everything"; that must never be a typo away."""
    session = _aged_session(tmp_path, "01JZERORANGE000000000000", days=900)
    result = runner.invoke(
        session_group, ["prune", "--older-than", "0d", "--records"],
        obj=_ctx(tmp_path, yes=True),
    )
    assert result.exit_code != 0
    assert session.exists()


def test_prune_keep_last_protects_recent_sessions(
    runner: CliRunner, tmp_path: Path,
) -> None:
    """The floor survives a range that would otherwise take everything."""
    older = _aged_session(tmp_path, "01JFLOOR000000000000000A", days=900)
    newer = _aged_session(tmp_path, "01JFLOOR000000000000000B", days=800)
    data = _out(runner.invoke(
        session_group, ["prune", "--older-than", "30d", "--keep-last", "1", "--records"],
        obj=_ctx(tmp_path, yes=True),
    ))
    assert data["protected_recent"] == 1
    assert newer.exists(), "the most recent session is protected"
    assert not older.exists()


def test_prune_orphans_only_touches_unreferenced_blobs(
    runner: CliRunner, tmp_path: Path,
) -> None:
    sha = "a" * 64
    session = _aged_session(tmp_path, "01JORPHANS000000000000A", days=900, sha=sha)
    referenced = _write_blob(tmp_path, sha, {"payload": True})
    orphan = _write_blob(tmp_path, "c" * 64, {"orphan": True})

    data = _out(runner.invoke(
        session_group, ["prune", "--orphans"], obj=_ctx(tmp_path, yes=True),
    ))
    assert str(orphan) in data["removed_blobs"]
    assert not orphan.exists()
    assert referenced.exists() and session.exists()


def test_prune_rejects_an_unreadable_duration(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        session_group, ["prune", "--older-than", "90"], obj=_ctx(tmp_path, yes=True),
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# revert
# ---------------------------------------------------------------------------

def test_revert_refuses_to_execute_without_allow_write(
    runner: CliRunner, tmp_path: Path,
) -> None:
    result = runner.invoke(
        session_group,
        ["revert", "01JXXXX000000000000000000", "--execute"],
        obj=_ctx(tmp_path),
    )
    assert result.exit_code != 0
    blob = result.output + (str(result.exception) if result.exception else "")
    assert "--allow-write" in blob


def test_revert_refuses_to_execute_without_yes(
    runner: CliRunner, tmp_path: Path,
) -> None:
    result = runner.invoke(
        session_group,
        ["revert", "01JXXXX000000000000000000", "--execute"],
        obj=_ctx(tmp_path, allow_write=True),
    )
    assert result.exit_code != 0
    blob = result.output + (str(result.exception) if result.exception else "")
    assert "--yes" in blob


def test_revert_dry_run_plan(runner: CliRunner, tmp_path: Path) -> None:
    """Dry-run plan rendering (needs session_revert.build_plan, worker D).

    Skipped until :mod:`bidkit_cli.session_revert` lands; kept collectible so it
    activates automatically once the dependency exists.
    """
    pytest.importorskip("bidkit_cli.session_revert")
    _write_session(
        tmp_path, session_id="01JREVERT0000000000000000", stamp="20260101T120000Z",
        records=[
            _rec(0, "invocation"),
            _rec(
                1, "op", operation_id="createOffer",
                reverse_hint={"op": "sell_inventory.deleteOffer",
                              "args": {"offer_id": "O1"}},
            ),
            _rec(2, "end", exit_code=0),
        ],
    )
    data = _out(runner.invoke(
        session_group, ["revert", "01JREVERT0000000000000000"], obj=_ctx(tmp_path),
    ))
    assert data["executed"] is False
    # Blocked/irreversible steps are always present in the payload, even empty.
    assert "blocked" in data


def test_revert_global_dry_run_overrides_execute(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global --dry-run overrides --execute: no gates, no dispatch, executed=false.

    --dry-run is the safer flag, so combined with --execute the command previews
    the plan instead of running it. The write/--yes gates a real execution needs
    are not enforced (this succeeds without them), and ``execute_plan`` is never
    called — the payload reports ``executed: false`` with empty ``results``,
    never a misleading "ok" execution. Ordinary ``--execute`` (without the
    global --dry-run) still refuses without the gates (covered above).
    """
    pytest.importorskip("bidkit_cli.session_revert")
    _write_session(
        tmp_path, session_id="01JDRYRUN0000000000000000", stamp="20260101T120000Z",
        records=[
            _rec(0, "invocation"),
            _rec(
                1, "op", operation_id="sell_inventory.createOffer",
                ids={"offer_id": "O1"}, classification="write",
            ),
            _rec(2, "end", exit_code=0),
        ],
    )

    def _must_not_run(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("execute_plan must not run under global --dry-run")

    monkeypatch.setattr("bidkit_cli.session_revert.execute_plan", _must_not_run)

    # No --allow-write/--yes: the dry-run override must not require them, and
    # exit 0 proves the gates were skipped rather than raised.
    data = _out(runner.invoke(
        session_group,
        ["revert", "01JDRYRUN0000000000000000", "--execute"],
        obj=_ctx(tmp_path, dry_run=True),
    ))
    assert data["executed"] is False
    assert data["results"] == []
    # The plan itself is still produced, so the preview is useful rather than a
    # misleading empty "ok" result.
    assert data["steps"]
    assert data["steps"][0]["operation_key"] == "sell_inventory.deleteOffer"
