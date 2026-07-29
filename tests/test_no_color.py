"""``--no-color`` is effective across every Rich table path.

The global ``--no-color`` flag must reach the console that every table
constructs, and that console must drop ALL ANSI style/color escapes — not just
color: Rich's own ``no_color`` keeps text styles such as bold, so the table
headers would still emit ``\\x1b[1m``. Console construction is centralized in
:func:`bidkit_cli.rendering.make_table_console`, which disables the whole color
system (``color_system=None``) when the flag is set, the one switch that drops
every escape.

These tests are offline and deterministic:

* the shared helper itself, with ``force_terminal=True`` both ways — the core
  guarantee that ``--no-color`` strips every escape, and that it is the active
  switch rather than a flag that is merely stored;
* :func:`render_table` (the generated-operation table path) forwarding the flag;
* the ``api list``/``search`` and ``session list`` table paths plumbing the flag
  through to the shared helper via a spy — under ``CliRunner`` those tables
  print to a non-TTY and would already be colorless, so a spy is the honest way
  to prove the flag reaches the helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from bidkit_cli import rendering
from bidkit_cli.app import cli
from bidkit_cli.commands.session import session_group
from bidkit_cli.context import CliContext

ESC = "\x1b"


def _styled_table() -> Any:
    """A table carrying both a color (cyan) and a style (bold header)."""
    from rich.table import Table

    table = Table(title="ops", show_lines=False, header_style="bold")
    table.add_column("METHOD", style="cyan", no_wrap=True)
    table.add_column("OPERATION")
    table.add_row("GET", "sell_inventory.getInventoryItems")
    return table


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Shared helper: the effective switch
# ---------------------------------------------------------------------------

def test_make_table_console_no_color_strips_all_ansi() -> None:
    """With --no-color even a forced-terminal console emits no ANSI escapes."""
    console = rendering.make_table_console(no_color=True, force_terminal=True)
    with console.capture() as capture:
        console.print(_styled_table())
    assert ESC not in capture.get()


def test_make_table_console_color_keeps_escapes() -> None:
    """Without --no-color the forced-terminal console still styles, proving the
    flag is the active switch rather than a no-op that always strips."""
    console = rendering.make_table_console(no_color=False, force_terminal=True)
    with console.capture() as capture:
        console.print(_styled_table())
    assert ESC in capture.get()


def test_make_table_console_disables_color_system_under_no_color() -> None:
    """no_color routes through color_system=None, the switch that drops styles too.

    Rich's own ``no_color`` keeps bold, so disabling the color system is what
    actually strips every escape. The helper ties the flag to ``color_system``
    (rather than to Rich's ``no_color``) so a table header cannot leave bold
    escapes behind when the flag is set.
    """
    assert rendering.make_table_console(
        no_color=True, force_terminal=True
    ).color_system is None
    assert rendering.make_table_console(
        no_color=False, force_terminal=True
    ).color_system is not None


# ---------------------------------------------------------------------------
# render_table (generated-operation table path) forwards no_color
# ---------------------------------------------------------------------------

def test_render_table_forwards_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """render_table forwards no_color to the shared console (generated-op path).

    ``_force_terminal()`` is forced True so a non-TTY test run exercises the
    color-emitting path; only ``no_color=True`` then strips the escapes, proving
    the flag is wired through rather than ignored.
    """
    monkeypatch.setattr(rendering, "_force_terminal", lambda: True)
    data = {
        "item_summaries": [
            {"itemId": "1", "title": "Vase"},
            {"itemId": "2", "title": "Cup"},
        ]
    }

    assert ESC not in rendering.render_table(data, title="ops", no_color=True)
    assert ESC in rendering.render_table(data, title="ops", no_color=False)


# ---------------------------------------------------------------------------
# api list/search table plumbing -> shared helper
# ---------------------------------------------------------------------------

def _spy_make_table_console(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Record the no_color each table path passes to the shared helper.

    Delegates to the real constructor so the table still renders; only the
    ``no_color`` argument is observed.
    """
    seen: list[bool] = []
    original = rendering.make_table_console

    def spy(*, no_color: bool, force_terminal: bool | None = None) -> Any:
        seen.append(no_color)
        return original(no_color=no_color, force_terminal=force_terminal)

    monkeypatch.setattr(rendering, "make_table_console", spy)
    return seen


def test_api_list_table_plumbs_no_color_true(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``api list --format table --no-color`` reaches the helper with no_color=True."""
    seen = _spy_make_table_console(monkeypatch)
    result = runner.invoke(cli, ["api", "list", "--format", "table", "--no-color"])
    assert result.exit_code == 0, result.output
    assert seen == [True], "api list --format table must route through the helper"


def test_api_list_table_plumbs_no_color_false(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the flag the helper is reached with no_color=False (preserved)."""
    seen = _spy_make_table_console(monkeypatch)
    result = runner.invoke(cli, ["api", "list", "--format", "table"])
    assert result.exit_code == 0, result.output
    assert seen == [False]


def test_api_search_table_plumbs_no_color(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``api search`` shares the same table path and no_color plumbing."""
    seen = _spy_make_table_console(monkeypatch)
    result = runner.invoke(
        cli, ["api", "search", "inventory", "--format", "table", "--no-color"]
    )
    assert result.exit_code == 0, result.output
    assert seen and seen[-1] is True


# ---------------------------------------------------------------------------
# session list table plumbing -> shared helper
# ---------------------------------------------------------------------------

def _session_ctx(tmp_path: Path, *, no_color: bool) -> CliContext:
    ctx = CliContext()
    ctx.output_format = "table"
    ctx.no_color = no_color
    ctx.sessions_dir = str(tmp_path)
    return ctx


def test_session_list_table_plumbs_no_color_true(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """``session list`` (table path) reaches the helper with no_color=True."""
    seen = _spy_make_table_console(monkeypatch)
    result = runner.invoke(
        session_group, ["list"], obj=_session_ctx(tmp_path, no_color=True),
    )
    assert result.exit_code == 0, result.output
    assert seen and seen[-1] is True


def test_session_list_table_plumbs_no_color_false(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Without the flag the session table helper is reached with no_color=False."""
    seen = _spy_make_table_console(monkeypatch)
    result = runner.invoke(
        session_group, ["list"], obj=_session_ctx(tmp_path, no_color=False),
    )
    assert result.exit_code == 0, result.output
    assert seen and seen[-1] is False
