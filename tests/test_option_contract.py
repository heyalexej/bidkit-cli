"""Option-contract tests: global derivation, request-option parity, freshness.

These assert the *observable* contracts of the option plumbing rather than
private implementation constants:

* the global option surface is derived from the root's own declarations, so
  every root spelling (including the secondary ``--compact``) is reordered as
  global and protected by the collision check — and reordering is stable whether
  the flag comes before or after the command path;
* the request escape-hatch options (``--query``/``--header``/``--path``/
  ``--allow-unknown-params`` plus the body suite) have identical destination,
  multiplicity, flag-ness, help, and relative order on ``api call`` and a
  generated command, and ``api call``'s ``--allow-unknown-params`` carries help;
* the option factories hand out fresh ``click.Option`` instances every call;
* compact JSON ends in exactly one trailing newline;
* :func:`public_poll_options` pins ``--wait``/``--poll`` destinations, defaults,
  ``show_default``, and the strictly-positive ``--poll`` bound.

No network and no credentials are required: every command exercised is either
offline (``api describe``), a ``--dry-run`` preview, or a synthetic command
built purely to inspect Click's parameter model.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from typing import Any

import click
import pytest
from click.testing import CliRunner

from bidkit_cli.app import (
    _assert_no_global_option_collision,
    _reorder_global_options,
    cli,
)
from bidkit_cli.commands.options import (
    make_all_body_options,
    make_allow_unknown_params_option,
    make_body_options_for_kind,
    make_header_option,
    make_path_option,
    make_query_option,
    make_universal_options,
    public_poll_options,
)
from bidkit_cli.rendering import emit_json


def _subgroup(parent: click.Command, name: str) -> click.Group:
    """Resolve ``name`` under ``parent`` as a nested group.

    The generated command tree is a known nested-Group structure; narrowing
    each hop with an assertion keeps the tree reads literal instead of widening
    to ``Any``.
    """
    assert isinstance(parent, click.Group)
    child = parent.commands[name]
    assert isinstance(child, click.Group)
    return child


# A representative generated GET command with the universal escape hatches and
# no request body, used for parity comparisons against ``api call``.
API_CALL = _subgroup(cli, "api").commands["call"]
GENERATED_GET = (
    _subgroup(_subgroup(cli, "sell"), "inventory").commands["get-inventory-items"]
)
DESCRIBE_OP = "sell_inventory.getInventoryItems"

# Every option spelling the root group actually declares — the observable
# source of truth for "what is global". Computed once from the public Click
# structure (primary + secondary opts), never from the derived private sets.
ROOT_OPTION_SPELLINGS = sorted(
    {
        spelling
        for param in cli.params
        if isinstance(param, click.Option)
        for spelling in (*param.opts, *param.secondary_opts)
    }
)

UNIVERSAL_OPTIONS = ("--query", "--header", "--path", "--allow-unknown-params")
BODY_OPTIONS = ("--body", "--body-json", "--body-file", "--file", "--field")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _option_meta(command: click.Command) -> dict[str, tuple[str, bool, bool, str]]:
    """Primary opt -> (dest, multiple, is_flag, help) for a command's options."""
    return {
        param.opts[0]: (param.name, param.multiple, param.is_flag, param.help or "")
        for param in command.params
        if isinstance(param, click.Option)
    }


def _option_order(command: click.Command) -> list[str]:
    """Primary opt names in declared order (the --help ordering)."""
    return [
        param.opts[0]
        for param in command.params
        if isinstance(param, click.Option)
    ]


def _filter(order: list[str], wanted: tuple[str, ...]) -> list[str]:
    return [name for name in order if name in wanted]


# ---------------------------------------------------------------------------
# Global option derivation + argv reordering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spelling", ROOT_OPTION_SPELLINGS)
def test_collision_check_protects_every_root_spelling(spelling: str) -> None:
    """Each root-declared spelling is recognized as global by the collision check.

    Parity between the derived global set and the root's declarations: every
    spelling observable on the root (including ``--compact``) is forbidden on a
    leaf, so the reorderer cannot silently steal it.
    """

    @click.group()
    def root() -> None:
        pass

    @root.command()
    @click.option(spelling, is_flag=True)
    def leaf(**_: Any) -> None:
        pass

    with pytest.raises(RuntimeError, match="global-option collision"):
        _assert_no_global_option_collision(root)


def test_compact_secondary_spelling_is_a_global_flag(runner: CliRunner) -> None:
    """``--compact`` (the secondary half of the pretty switch) reorders as a flag.

    Placed AFTER the command path it still binds to the root and produces
    compact JSON — proving the secondary spelling is in the global flag set and
    does not eat the following token as a value.
    """
    result = runner.invoke(
        cli, ["api", "describe", DESCRIBE_OP, "--format", "json", "--compact"]
    )
    assert result.exit_code == 0, result.output
    # Compact JSON is a single line per value: no two-space object indentation.
    assert '\n  "' not in result.output
    assert json.loads(result.output)["key"] == DESCRIBE_OP


def test_pretty_primary_spelling_is_a_global_flag(runner: CliRunner) -> None:
    """``--pretty`` after the command path yields indented JSON."""
    result = runner.invoke(
        cli, ["api", "describe", DESCRIBE_OP, "--format", "json", "--pretty"]
    )
    assert result.exit_code == 0, result.output
    assert '\n  "' in result.output  # two-space indentation present


def test_global_value_option_consumes_value_after_command(
    runner: CliRunner,
) -> None:
    """A value option (``--format json``) after the command still binds its value."""
    result = runner.invoke(
        cli, ["api", "describe", DESCRIBE_OP, "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["key"] == DESCRIBE_OP


def test_reordering_is_stable_before_or_after_command(runner: CliRunner) -> None:
    """Globals before the command and after it produce identical previews.

    The reorderer is value-preserving and order-stable: hoisting ``--dry-run``
    and ``--format`` from the tail must not change the parsed request.
    """
    before = runner.invoke(
        cli,
        ["--dry-run", "--format", "json", "sell", "inventory", "get-inventory-items"],
    )
    after = runner.invoke(
        cli,
        ["sell", "inventory", "get-inventory-items", "--dry-run", "--format", "json"],
    )
    assert before.exit_code == 0, before.output
    assert after.exit_code == 0, after.output
    assert before.output == after.output


def test_reorderer_preserves_help_token_position() -> None:
    """``-h``/``--help`` stay in place so a subcommand's own help still wins."""
    reordered = _reorder_global_options(
        ["sell", "inventory", "--help", "--dry-run"]
    )
    # Globals are hoisted to the front; --help is NOT (it stays where typed).
    assert reordered[0] == "--dry-run"
    assert reordered.index("--help") > reordered.index("inventory")


# ---------------------------------------------------------------------------
# Request escape-hatch option parity (api call <-> generated command)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", UNIVERSAL_OPTIONS)
def test_universal_option_metadata_matches_api_call(name: str) -> None:
    """Each universal option has identical dest/multiple/flag/help on both surfaces."""
    api_meta = _option_meta(API_CALL)[name]
    gen_meta = _option_meta(GENERATED_GET)[name]
    assert api_meta == gen_meta


def test_universal_option_relative_order_matches() -> None:
    """The four universal options share one relative order on both surfaces."""
    assert _filter(_option_order(API_CALL), UNIVERSAL_OPTIONS) == list(UNIVERSAL_OPTIONS)
    assert _filter(_option_order(GENERATED_GET), UNIVERSAL_OPTIONS) == list(
        UNIVERSAL_OPTIONS
    )


def test_api_call_exposes_all_body_options_in_canonical_order() -> None:
    """``api call`` offers the full body suite in the documented order."""
    assert _filter(_option_order(API_CALL), BODY_OPTIONS) == list(BODY_OPTIONS)


def test_api_call_allow_unknown_params_has_help() -> None:
    """The previously-missing help for ``--allow-unknown-params`` is now present."""
    _, _, _, help_text = _option_meta(API_CALL)["--allow-unknown-params"]
    assert help_text.strip() != ""


def test_generated_json_body_exposes_only_body_and_body_json(
    manifest: Any,
) -> None:
    """A JSON-body generated command exposes only --body/--body-json from the suite."""
    command = (
        _subgroup(_subgroup(cli, "sell"), "inventory")
        .commands["create-or-replace-inventory-item"]
    )
    assert _filter(_option_order(command), BODY_OPTIONS) == ["--body", "--body-json"]


def test_generated_multipart_file_help_lists_operation_file_fields(
    manifest: Any,
) -> None:
    """A multipart command names its file fields in --file's help."""
    command = (
        _subgroup(_subgroup(cli, "commerce"), "media")
        .commands["create-image-from-file"]
    )
    file_option = next(
        param
        for param in command.params
        if isinstance(param, click.Option) and "--file" in param.opts
    )
    assert "Files: image" in (file_option.help or "")


def test_api_call_usage_keeps_positional_arguments_first() -> None:
    """``api call`` Usage line still leads with SERVICE [OPERATION]."""
    runner = CliRunner()
    result = runner.invoke(cli, ["api", "call", "--help"])
    assert result.exit_code == 0, result.output
    first_line = result.output.splitlines()[0]
    assert "SERVICE [OPERATION]" in first_line


# ---------------------------------------------------------------------------
# Factory freshness (no shared mutable Parameter instances)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "factory",
    [
        make_query_option,
        make_header_option,
        make_path_option,
        make_allow_unknown_params_option,
    ],
)
def test_single_factory_returns_fresh_instances(factory: Any) -> None:
    """Two calls yield distinct Option instances with identical observable metadata."""
    first = factory()
    second = factory()
    assert first is not second
    assert first.opts == second.opts
    assert first.name == second.name
    assert first.multiple == second.multiple
    assert first.is_flag == second.is_flag
    assert first.help == second.help


def test_make_universal_options_returns_four_fresh_options() -> None:
    """The universal list has the four escape hatches, all fresh per call."""
    first = make_universal_options()
    second = make_universal_options()
    assert [opt.opts[0] for opt in first] == list(UNIVERSAL_OPTIONS)
    assert len(first) == len(second) == 4
    # No instance is shared within a list or across lists.
    seen: list[click.Option] = []
    for option in (*first, *second):
        assert option not in seen
        seen.append(option)


def test_make_all_body_options_matches_canonical_order_and_dests() -> None:
    """The full body suite is built in canonical order with pinned destinations."""
    options = make_all_body_options()
    assert [opt.opts[0] for opt in options] == list(BODY_OPTIONS)
    assert [opt.name for opt in options] == [
        "body_arg",
        "body_json",
        "body_file",
        "file_pairs",
        "field_pairs",
    ]


def test_make_body_options_for_kind_unknown_yields_nothing() -> None:
    """An unrecognized body kind exposes no body options (not a wrong subset)."""
    assert make_body_options_for_kind("none") == []
    assert make_body_options_for_kind("no-such-kind") == []


# ---------------------------------------------------------------------------
# Compact JSON: exactly one trailing newline
# ---------------------------------------------------------------------------

def test_compact_json_has_exactly_one_trailing_newline() -> None:
    """Compact emit_json is one line terminated by exactly one newline."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        emit_json({"a": 1, "b": [1, 2, 3]}, pretty=False)
    output = buffer.getvalue()
    assert output.endswith("\n")
    assert not output.endswith("\n\n")
    # Compact: no internal newlines — exactly the one trailing terminator.
    assert output.count("\n") == 1


def test_pretty_json_indented_and_single_trailing_newline() -> None:
    """Pretty emit_json indents but still ends in exactly one newline."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        emit_json({"a": 1, "b": [1, 2, 3]}, pretty=True)
    output = buffer.getvalue()
    assert output.endswith("\n")
    assert not output.endswith("\n\n")
    assert output.count("\n") > 1  # internal indentation newlines present


def test_cli_compact_output_ends_with_single_newline(runner: CliRunner) -> None:
    """The wired CLI compact path also ends in exactly one newline."""
    result = runner.invoke(
        cli, ["api", "describe", DESCRIBE_OP, "--format", "json", "--compact"]
    )
    assert result.exit_code == 0, result.output
    assert result.output.endswith("\n")
    assert not result.output.endswith("\n\n")


# ---------------------------------------------------------------------------
# public_poll_options contract
# ---------------------------------------------------------------------------

def _poll_command() -> click.Command:
    """A synthetic command carrying only the public polling options."""

    @click.command()
    @public_poll_options()
    def _cmd(wait_seconds: float, poll_interval: float) -> None:
        pass

    return _cmd


def test_public_poll_options_pins_destinations_defaults_and_types() -> None:
    """--wait/--poll map to wait_seconds/poll_interval with the documented bounds."""
    command = _poll_command()
    by_opt = {
        param.opts[0]: param
        for param in command.params
        if isinstance(param, click.Option)
    }
    wait = by_opt["--wait"]
    poll = by_opt["--poll"]

    assert wait.name == "wait_seconds"
    assert poll.name == "poll_interval"

    assert wait.default == 0.0
    assert poll.default == 15.0
    assert wait.show_default is True
    assert poll.show_default is True

    assert isinstance(wait.type, click.FloatRange)
    assert wait.type.min == 0
    assert wait.type.min_open is False  # 0 is allowed

    assert isinstance(poll.type, click.FloatRange)
    assert poll.type.min == 0
    assert poll.type.min_open is True  # strictly positive: 0 rejected


def test_public_poll_options_renders_wait_before_poll() -> None:
    """--help lists --wait above --poll (the historical workflow ordering)."""
    command = _poll_command()
    order = [param.opts[0] for param in command.params if isinstance(param, click.Option)]
    assert order.index("--wait") < order.index("--poll")


def test_poll_zero_is_rejected_wait_zero_is_accepted() -> None:
    """The strictly-positive --poll bound rejects 0; --wait accepts 0."""
    command = _poll_command()
    runner = CliRunner()

    rejected = runner.invoke(command, ["--poll", "0"])
    assert rejected.exit_code == 2  # Click usage error from FloatRange

    accepted = runner.invoke(command, ["--wait", "0", "--poll", "1"])
    assert accepted.exit_code == 0, accepted.output


def test_public_poll_options_factory_is_fresh_per_application() -> None:
    """Two commands decorated independently do not share Option instances."""

    @click.command()
    @public_poll_options()
    def first(wait_seconds: float, poll_interval: float) -> None:
        pass

    @click.command()
    @public_poll_options()
    def second(wait_seconds: float, poll_interval: float) -> None:
        pass

    first_opts = {
        param.opts[0]: param for param in first.params if isinstance(param, click.Option)
    }
    second_opts = {
        param.opts[0]: param for param in second.params if isinstance(param, click.Option)
    }
    for name in ("--wait", "--poll"):
        assert first_opts[name] is not second_opts[name]


# ---------------------------------------------------------------------------
# Root numeric option ranges: --timeout / --max-retries / --wait-for-live
#
# These global options used to accept any float/int, so a typo like
# ``--timeout -1`` silently produced a nonsensical config (or a late internal
# error). They now declare a non-negative Click Range, so a negative value is a
# usage error at parse time (exit 2) while zero stays valid.
# ---------------------------------------------------------------------------

ROOT_NUMERIC_OPTIONS = ("--timeout", "--max-retries", "--wait-for-live")


def test_root_numeric_options_declare_non_negative_ranges() -> None:
    """Each bounded root option declares a Click Range with min=0 (zero valid)."""
    by_opt = {p.opts[0]: p for p in cli.params if isinstance(p, click.Option)}
    timeout = by_opt["--timeout"]
    max_retries = by_opt["--max-retries"]
    wait_for_live = by_opt["--wait-for-live"]
    assert isinstance(timeout.type, click.FloatRange)
    assert timeout.type.min == 0
    assert timeout.type.min_open is False  # 0 stays valid
    assert isinstance(max_retries.type, click.IntRange)
    assert max_retries.type.min == 0
    assert max_retries.type.min_open is False
    assert isinstance(wait_for_live.type, click.FloatRange)
    assert wait_for_live.type.min == 0
    assert wait_for_live.type.min_open is False


@pytest.mark.parametrize("flag", ROOT_NUMERIC_OPTIONS)
def test_root_numeric_option_rejects_negative(runner: CliRunner, flag: str) -> None:
    """A negative value is a Click usage error (exit 2), not a silent bad value."""
    result = runner.invoke(
        cli, ["api", "describe", DESCRIBE_OP, "--format", "json", flag, "-1"]
    )
    assert result.exit_code == 2, result.output
    assert flag in result.output


@pytest.mark.parametrize("flag", ROOT_NUMERIC_OPTIONS)
def test_root_numeric_option_accepts_zero(runner: CliRunner, flag: str) -> None:
    """Zero stays valid for every bounded root numeric option."""
    result = runner.invoke(
        cli, ["api", "describe", DESCRIBE_OP, "--format", "json", flag, "0"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["key"] == DESCRIBE_OP
