"""Option-range contract for the handwritten ``bidkit session`` numeric options.

The session commands' handwritten numeric options reject out-of-range values at
Click's parameter boundary (a usage error, exit 2) instead of producing an
internal ``ValueError`` deep in the recorder/revert planner or silently-empty
results:

* ``--since`` / ``--limit`` (``list`` and ``grep``) and ``--keep-last``
  (``prune``) accept ``>= 0`` — zero stays meaningful where it already was
  (``--since 0`` = "started since now", ``--limit 0`` = "show none",
  ``--keep-last 0`` = "protect none").
* ``--last`` (``revert``) accepts ``>= 0``.
* ``--seq`` (``revert``) accepts ``>= 1``: seq 0 is always the invocation
  record, never a revertible op, so exposing 0 over the CLI would only mislead.

These rejections happen during Click parsing, so they need no recorder
implementation (:mod:`bidkit_cli.session`) and no live sessions dir — only the
``session_group`` command tree. Positive ``revert`` parse tests additionally
exercise :mod:`bidkit_cli.session_revert` and are skipped if it is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import orjson
import pytest
from click.testing import CliRunner

from bidkit_cli.commands.session import session_group
from bidkit_cli.context import CliContext

# ---------------------------------------------------------------------------
# shared harness (mirrors test_session_commands.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _ctx(sessions_dir: Path, **kwargs: object) -> CliContext:
    """A CliContext pinned to a tmp sessions dir and JSON output."""
    ctx = CliContext()
    # sessions_dir is read via getattr, so setting it on the instance works.
    ctx.sessions_dir = str(sessions_dir)  # type: ignore[attr-defined]
    ctx.output_format = "json"
    ctx.pretty = False
    for key, value in kwargs.items():
        setattr(ctx, key, value)
    return ctx


def _usage_error(runner: CliRunner, args: list[str], sessions_dir: Path,
                 **ctx_kwargs: object):
    """Invoke session_group and assert Click rejected at parse time (exit 2)."""
    result = runner.invoke(session_group, args, obj=_ctx(sessions_dir, **ctx_kwargs))
    assert result.exit_code == 2, (
        f"expected a Click usage error (exit 2) for {args!r}, got "
        f"exit {result.exit_code}: {result.output}"
    )
    return result


def _write_minimal_session(base: Path, session_id: str = "01JREVERT0000000000000000",
                           stamp: str = "20260101T120000Z") -> None:
    """One session file with a single op record, for positive revert parses."""
    month = stamp[:6]
    folder = base / month
    folder.mkdir(parents=True, exist_ok=True)
    records = [
        {"v": 1, "type": "invocation", "ts": "2026-01-01T00:00:00.000Z",
         "session_id": session_id, "invocation_id": "INV", "seq": 0},
        {"v": 1, "type": "op", "ts": "2026-01-01T00:00:01.000Z",
         "session_id": session_id, "invocation_id": "INV", "seq": 1,
         "operation_id": "createOffer",
         "ids": {"offer_id": "O1"},
         "reverse_hint": {"op": "sell_inventory.deleteOffer", "args": {"offer_id": "O1"}}},
        {"v": 1, "type": "end", "ts": "2026-01-01T00:00:02.000Z",
         "session_id": session_id, "invocation_id": "INV", "seq": 2, "exit_code": 0},
    ]
    path = folder / f"{stamp}_{session_id}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(orjson.dumps(rec).decode() + "\n")


# ---------------------------------------------------------------------------
# --since / --limit  (list + grep)
# ---------------------------------------------------------------------------

def test_list_since_negative_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """--since -5 used to silently match 'the future'; now it is a usage error."""
    result = _usage_error(runner, ["list", "--since", "-5"], tmp_path)
    assert "--since" in result.output
    assert "x>=0" in result.output or "minimum" in result.output.lower()


def test_list_limit_negative_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """--limit -1 used to cap to 0 (silent empty); now it is a usage error."""
    result = _usage_error(runner, ["list", "--limit", "-1"], tmp_path)
    assert "--limit" in result.output


def test_list_since_zero_is_valid(runner: CliRunner, tmp_path: Path) -> None:
    """Zero stays meaningful: cutoff = now, so an empty dir yields count 0."""
    result = runner.invoke(session_group, ["list", "--since", "0"],
                           obj=_ctx(tmp_path))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["count"] == 0


def test_list_limit_zero_is_valid(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(session_group, ["list", "--limit", "0"],
                           obj=_ctx(tmp_path))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["count"] == 0


def test_grep_since_negative_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """The grep --since shares the same range contract as list --since."""
    result = _usage_error(runner, ["grep", "anything", "--since", "-2"], tmp_path)
    assert "--since" in result.output


# ---------------------------------------------------------------------------
# --keep-last  (prune)
# ---------------------------------------------------------------------------

def test_prune_keep_last_negative_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """Negatives are now a Click usage error, not the prior late UsageError."""
    result = _usage_error(
        runner, ["prune", "--orphans", "--keep-last", "-1"], tmp_path, yes=True,
    )
    assert "--keep-last" in result.output


def test_prune_keep_last_zero_is_valid(runner: CliRunner, tmp_path: Path) -> None:
    """Zero protects nothing; with --orphans it parses and previews cleanly."""
    result = runner.invoke(
        session_group, ["prune", "--orphans", "--keep-last", "0"],
        obj=_ctx(tmp_path),
    )
    assert result.exit_code == 0, result.output
    # Nothing to prune in an empty store, but the command ran and reported.
    payload = json.loads(result.output)
    assert payload["applied"] is False


# ---------------------------------------------------------------------------
# --last / --seq  (revert)
# ---------------------------------------------------------------------------

def test_revert_last_negative_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """--last -1 used to reach build_plan's internal ValueError; now Click stops it."""
    result = _usage_error(runner, ["revert", "01J", "--last", "-1"], tmp_path)
    assert "--last" in result.output


def test_revert_seq_zero_rejected(runner: CliRunner, tmp_path: Path) -> None:
    """seq 0 is the invocation record (never a revertible op): rejected at the CLI."""
    result = _usage_error(runner, ["revert", "01J", "--seq", "0"], tmp_path)
    assert "--seq" in result.output
    assert "x>=1" in result.output or "minimum" in result.output.lower()


def test_revert_seq_negative_rejected(runner: CliRunner, tmp_path: Path) -> None:
    result = _usage_error(runner, ["revert", "01J", "--seq", "-3"], tmp_path)
    assert "--seq" in result.output


def test_revert_last_zero_parses(runner: CliRunner, tmp_path: Path) -> None:
    """Zero is meaningful (revert the last 0 ops) once the planner is present."""
    pytest.importorskip("bidkit_cli.session_revert")
    _write_minimal_session(tmp_path)
    result = runner.invoke(
        session_group,
        ["revert", "01JREVERT0000000000000000", "--last", "0"],
        obj=_ctx(tmp_path),
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["executed"] is False


def test_revert_seq_one_parses(runner: CliRunner, tmp_path: Path) -> None:
    """The smallest meaningful seq (1) reaches the planner and produces a plan."""
    pytest.importorskip("bidkit_cli.session_revert")
    _write_minimal_session(tmp_path)
    result = runner.invoke(
        session_group,
        ["revert", "01JREVERT0000000000000000", "--seq", "1"],
        obj=_ctx(tmp_path),
    )
    assert result.exit_code == 0, result.output
