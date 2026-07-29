"""Option/side-effect contract for the handwritten workflow commands.

Three narrow, offline concerns (no network, no live account):

* The shared ``--wait``/``--poll`` poll options on ``sell inventory
  verify-public``, ``test-run cleanup-report``, and ``test-run execute``
  (provided by ``bidkit_cli.commands.options.public_poll_options``):
  ``--wait`` is non-negative (default 0), ``--poll`` is strictly positive
  (default 15), and ``--wait`` precedes ``--poll`` in ``--help``.
* ``test-run execute`` preview modes (``--plan-only`` and the global
  ``--dry-run``) render an accurate plan but create/save/update NO local
  ledger; the normal non-preview path still persists.
* Executable example gate parity: a curated normal write
  (``commerce_media.createImageFromFile``) advertises ``--allow-write`` (not
  the expert/destructive gates), while unclassified unknown-risk POSTs
  (``uploadPostOrderDocument``, ``uploadVideo``, ``issueRefund``) advertise
  ``--allow-write-expert --yes``.

The poll/ledger tests import the CLI, which transitively imports
``bidkit_cli.commands.options`` once worker B lands it; until then they skip
cleanly via ``importorskip``. The example-gate tests import only the example
generator and the manifest, so they run standalone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bidkit_cli.examples import examples_for

# ---------------------------------------------------------------------------
# shared harness
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _cli():
    """The full CLI; skips until the shared options module has landed."""
    pytest.importorskip("bidkit_cli.commands.options")
    from bidkit_cli.app import cli

    return cli


def _tokens(command: str) -> list[str]:
    return command.split()


# ---------------------------------------------------------------------------
# Polling options: range, default, help order  (skip until options.py lands)
# ---------------------------------------------------------------------------

def test_verify_public_wait_default_is_zero(runner: CliRunner) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--dry-run", "--format", "json",
    ])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["wait_seconds"] == 0.0


def test_verify_public_poll_default_is_fifteen(runner: CliRunner) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--dry-run", "--format", "json",
    ])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["poll_interval"] == 15.0


def test_verify_public_wait_negative_rejected(runner: CliRunner) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--wait", "-1", "--dry-run",
    ])
    assert r.exit_code == 2, r.output
    assert "--wait" in r.output


def test_verify_public_wait_zero_accepted(runner: CliRunner) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--wait", "0", "--dry-run", "--format", "json",
    ])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["wait_seconds"] == 0.0


def test_verify_public_poll_zero_rejected(runner: CliRunner) -> None:
    """--poll is strictly positive: 0 (or negative) is a Click usage error."""
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--poll", "0", "--dry-run",
    ])
    assert r.exit_code == 2, r.output
    assert "--poll" in r.output


def test_verify_public_poll_negative_rejected(runner: CliRunner) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--poll", "-5", "--dry-run",
    ])
    assert r.exit_code == 2, r.output
    assert "--poll" in r.output


def test_verify_public_help_orders_wait_before_poll(runner: CliRunner) -> None:
    """The shared poll options keep --wait ahead of --poll in --help output."""
    cli = _cli()
    r = runner.invoke(cli, ["sell", "inventory", "verify-public", "--help"])
    assert r.exit_code == 0, r.output
    out = r.output
    assert "--wait" in out and "--poll" in out
    assert out.index("--wait") < out.index("--poll")


def test_verify_public_expect_image_count_declares_non_negative_range() -> None:
    """--expect-image-count declares an IntRange with min=0 (zero valid)."""
    import click

    cli = _cli()
    cmd = cli.commands["sell"].commands["inventory"].commands["verify-public"]
    opt = next(
        p for p in cmd.params
        if isinstance(p, click.Option) and "--expect-image-count" in p.opts
    )
    assert isinstance(opt.type, click.IntRange)
    assert opt.type.min == 0
    assert opt.type.min_open is False  # 0 (an assertion, not a count) stays valid


def test_verify_public_expect_image_count_negative_rejected(
    runner: CliRunner,
) -> None:
    """A negative --expect-image-count is a Click usage error (exit 2)."""
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--expect-image-count", "-1", "--dry-run",
    ])
    assert r.exit_code == 2, r.output
    assert "--expect-image-count" in r.output


def test_verify_public_expect_image_count_zero_accepted(
    runner: CliRunner,
) -> None:
    """Zero stays valid and surfaces as an assertion in the preview."""
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "verify-public", "--listing-id", "1",
        "--expect-image-count", "0", "--dry-run", "--format", "json",
    ])
    assert r.exit_code == 0, r.output
    assert "expect_image_count" in json.loads(r.output)["assertions"]


def test_cleanup_report_exposes_poll_options(runner: CliRunner) -> None:
    """cleanup-report shares the same --wait/--poll surface and range contract."""
    cli = _cli()
    help_out = runner.invoke(
        cli, ["sell", "inventory", "test-run", "cleanup-report", "--help"]
    ).output
    assert "--wait" in help_out and "--poll" in help_out
    assert help_out.index("--wait") < help_out.index("--poll")

    # --poll 0 is rejected at the parse boundary (no run-id state needed).
    r = runner.invoke(cli, [
        "sell", "inventory", "test-run", "cleanup-report",
        "--run-id", "R", "--poll", "0",
    ])
    assert r.exit_code == 2, r.output
    assert "--poll" in r.output


def test_execute_exposes_poll_options(runner: CliRunner) -> None:
    """execute shares the same --wait/--poll surface and range contract."""
    cli = _cli()
    help_out = runner.invoke(
        cli, ["sell", "inventory", "test-run", "execute", "--help"]
    ).output
    assert "--wait" in help_out and "--poll" in help_out
    assert help_out.index("--wait") < help_out.index("--poll")

    r = runner.invoke(cli, [
        "sell", "inventory", "test-run", "execute", "--run-id", "R", "--poll", "0",
    ])
    assert r.exit_code == 2, r.output
    assert "--poll" in r.output


# ---------------------------------------------------------------------------
# Preview side effects: --plan-only / --dry-run must not write the ledger
# (skip until options.py lands)
# ---------------------------------------------------------------------------

def test_execute_plan_only_writes_no_ledger(runner: CliRunner, tmp_path: Path) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "test-run", "execute",
        "--run-id", "plan-only-run", "--source-sku", "S1", "--test-sku", "AAAAA",
        "--plan-only", "--ledger-dir", str(tmp_path), "--format", "json",
    ], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    plan = json.loads(r.output)
    # The in-memory merge still surfaces the seeds in the plan ...
    assert plan["source_skus"] == ["S1"]
    assert plan["test_skus"] == ["AAAAA"]
    # ... but no ledger (nor a leftover .tmp) was written.
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_execute_global_dry_run_writes_no_ledger(
    runner: CliRunner, tmp_path: Path,
) -> None:
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "test-run", "execute",
        "--run-id", "dry-run-run", "--source-sku", "S1",
        "--dry-run", "--ledger-dir", str(tmp_path), "--format", "json",
    ], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert not list(tmp_path.glob("*.json"))
    assert not list(tmp_path.rglob("*.tmp"))


def test_execute_plan_only_does_not_clobber_existing_ledger(
    runner: CliRunner, tmp_path: Path,
) -> None:
    """--plan-only may READ an existing ledger for an accurate plan, but must
    not modify it (no mtime/size change, no rewritten seeds)."""
    cli = _cli()
    # Seed a real ledger first (normal path persists it).
    runner.invoke(cli, [
        "sell", "inventory", "test-run", "execute",
        "--run-id", "existing-run", "--source-sku", "ORIG",
        "--ledger-dir", str(tmp_path), "--format", "json",
    ], catch_exceptions=False)
    ledger_path = tmp_path / "existing-run.json"
    assert ledger_path.exists(), "normal execute must persist the ledger"
    before = ledger_path.read_bytes()

    r = runner.invoke(cli, [
        "sell", "inventory", "test-run", "execute",
        "--run-id", "existing-run", "--source-sku", "EXTRA", "--plan-only",
        "--ledger-dir", str(tmp_path), "--format", "json",
    ], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    plan = json.loads(r.output)
    # The plan reflects the in-memory merge (reads the existing ledger, then
    # adds EXTRA) without mutating the file on disk.
    assert "ORIG" in plan["source_skus"]
    assert "EXTRA" in plan["source_skus"]
    assert ledger_path.read_bytes() == before


def test_execute_normal_path_persists_ledger(
    runner: CliRunner, tmp_path: Path,
) -> None:
    """Non-preview, non-cleanup execute keeps its documented side effect."""
    cli = _cli()
    r = runner.invoke(cli, [
        "sell", "inventory", "test-run", "execute",
        "--run-id", "normal-run", "--source-sku", "S1",
        "--ledger-dir", str(tmp_path), "--format", "json",
    ], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert (tmp_path / "normal-run.json").exists()


# ---------------------------------------------------------------------------
# Executable example gate parity  (offline: examples generator + manifest only)
# ---------------------------------------------------------------------------

def test_create_image_from_file_executable_uses_allow_write(manifest) -> None:
    """A curated NORMAL write advertises --allow-write, not the expert/destructive gates."""
    op = manifest.get("commerce_media.createImageFromFile")
    execs = [e for e in examples_for(op) if not e.safe]
    assert execs, "expected an executable example"
    for example in execs:
        toks = _tokens(example.command)
        assert "--allow-write" in toks
        assert "--allow-write-expert" not in toks
        assert "--yes" not in toks


def test_create_image_from_file_keeps_dry_run_preview(manifest) -> None:
    op = manifest.get("commerce_media.createImageFromFile")
    safe = [e.command for e in examples_for(op) if e.safe]
    assert any("--dry-run" in cmd for cmd in safe)


def test_publish_offer_executable_uses_allow_write_only(manifest) -> None:
    """publishOffer is a normal write: --allow-write, never --yes."""
    op = manifest.get("sell_inventory.publishOffer")
    execs = [e for e in examples_for(op) if not e.safe]
    assert execs, "expected an executable example"
    for example in execs:
        toks = _tokens(example.command)
        assert "--allow-write" in toks
        assert "--allow-write-expert" not in toks
        assert "--yes" not in toks


def test_unknown_risk_uploads_require_expert_and_yes(manifest) -> None:
    """Unclassified upload POSTs need both --allow-write-expert and --yes."""
    for key in ("commerce_media.uploadPostOrderDocument", "commerce_media.uploadVideo"):
        op = manifest.get(key)
        execs = [e for e in examples_for(op) if not e.safe]
        assert execs, f"{key}: expected an executable example"
        for example in execs:
            toks = _tokens(example.command)
            assert "--allow-write-expert" in toks, f"{key}: {example.command}"
            assert "--yes" in toks, f"{key}: {example.command}"


def test_issue_refund_executable_requires_expert_and_yes(manifest) -> None:
    """issueRefund is a signed unknown-risk POST: --allow-write-expert --yes."""
    op = manifest.get("sell_fulfillment.issueRefund")
    execs = [e for e in examples_for(op) if not e.safe]
    assert execs, "expected an executable example"
    for example in execs:
        toks = _tokens(example.command)
        assert "--allow-write-expert" in toks
        assert "--yes" in toks
