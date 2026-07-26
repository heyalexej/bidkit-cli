"""The root ``bidkit`` Click application and global option contract (spec §7, §8).

Global options are defined once and attached to the root group; nested groups
and commands read them from ``ctx.obj`` (a :class:`CliContext`). The static
command groups (api, auth, config, version, completion) and the generated
namespace groups (buy, commerce, developer, post-order, sell) are wired together
in :func:`build_cli`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import click

from .context import CliContext
from .errors import CliError, report_error
from .manifest import assert_sdk_compatible, load_manifest

LOG_LEVELS = ["quiet", "warning", "info", "debug"]


def _parse_test_provenance(raw: str | None) -> dict[str, str] | None:
    """Parse the ``--test-provenance`` JSON map into a ``{field: source_sku}``.

    Accepts ``{"title":"SKU_A","image":"SKU_B",...}``; a non-dict payload is a
    usage error so an agent cannot silently disable provenance by passing junk.
    """
    if not raw:
        return None
    import orjson

    try:
        parsed = orjson.loads(raw)
    except orjson.JSONDecodeError as exc:
        raise CliError(
            "--test-provenance must be a JSON object, e.g. "
            "'{\"title\":\"SKU_A\",\"image\":\"SKU_B\"}': {exc.msg}"
        ) from exc
    if not isinstance(parsed, dict):
        raise CliError("--test-provenance must be a JSON object mapping field -> source sku.")
    return {str(k): str(v) for k, v in parsed.items() if v}

# Global options (spec §8) that may appear anywhere on the command line, including
# after the command path (e.g. `bidkit sell inventory ... --dry-run`). Click only
# parses group-level options before the subcommand, so main() reorders these
# tokens to the front before invoking Click. Help flags stay in place so each
# command's own --help still wins.
_GLOBAL_VALUE_OPTIONS = {
    "--config", "--environment", "--marketplace", "--format", "--output-file",
    "--timeout", "--max-retries", "--log-level", "--select",
    "--content-language", "--wait-for-live",
    "--test-marker", "--test-run-id", "--test-provenance", "--ledger-dir",
}
_GLOBAL_FLAG_OPTIONS = {
    "--trace", "--no-color", "--allow-write", "--allow-write-expert",
    "--yes", "--dry-run", "--force", "--pretty", "--compact", "--include-meta",
    "--marketplace-locale", "--merge", "--verify-live",
    "--test-mode", "--allow-scrambled-test-data", "--allow-untracked-test-run",
}


def _reorder_global_options(argv: list[str]) -> list[str]:
    """Move recognized global option tokens to the front of argv.

    Returns a new argv with all global options gathered before the first
    non-global token, so Click's root group parses them regardless of where the
    user typed them. `--opt=value` and `--opt value` forms are both handled.
    """
    globals_: list[str] = []
    rest: list[str] = []
    i = 0
    skip_next_value = False
    while i < len(argv):
        token = argv[i]
        if skip_next_value:
            globals_.append(token)
            skip_next_value = False
            i += 1
            continue
        if token in {"-h", "--help"}:
            # Help is positional/contextual: leave it exactly where it is.
            rest.append(token)
            i += 1
            continue
        if "=" in token and token.split("=", 1)[0] in _GLOBAL_VALUE_OPTIONS:
            globals_.append(token)
            i += 1
            continue
        if token in _GLOBAL_FLAG_OPTIONS:
            globals_.append(token)
            i += 1
            continue
        if token in _GLOBAL_VALUE_OPTIONS:
            globals_.append(token)
            # Consume the following token as the option's value, if present.
            if i + 1 < len(argv):
                skip_next_value = True
            i += 1
            continue
        rest.append(token)
        i += 1
    return [*globals_, *rest]


# Every global option name (value + flag). Used by the build-time collision
# check so a leaf command can never silently redeclare one.
_ALL_GLOBAL_OPTION_NAMES = _GLOBAL_VALUE_OPTIONS | _GLOBAL_FLAG_OPTIONS


def _requested_json_mode(argv: list[str]) -> bool:
    """Whether the agent asked for JSON-shaped errors.

    The error shape must follow the *requested* ``--format`` rather than
    stdout's TTY-ness, so ``--format json`` on a TTY emits a JSON error and
    ``--format text`` when piped emits a text error.
    """
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--format":
            return i + 1 < len(argv) and argv[i + 1] == "json"
        if token.startswith("--format="):
            return token.split("=", 1)[1] == "json"
        i += 1
    return not sys.stdout.isatty()


def _assert_no_global_option_collision(group: click.Group) -> None:
    """Fail fast if a leaf command declares an option that is also global.

    The root argv reorderer hoists every global option token to the front so it
    binds to the root group; a leaf command that *also* declares the same
    ``--name`` can never receive the value (consumed globally first). We forbid
    the collision at build time so it cannot regress.
    """
    problems: list[str] = []
    for path, command in _walk_leaf_commands(group):
        for param in command.params:
            for opt in param.opts:
                if opt in _ALL_GLOBAL_OPTION_NAMES:
                    problems.append(f"{path}: command declares {opt!r}, a global option")
    if problems:
        raise RuntimeError(
            "global-option collision; re-read the value from "
            "ctx.obj instead of declaring it locally:\n  " + "\n  ".join(problems)
        )


def _walk_leaf_commands(group: click.Group, prefix: str = ""):
    """Yield (dotted-path, command) for every leaf (non-group) command."""
    for name, command in group.commands.items():
        path = f"{prefix} {name}".strip()
        if isinstance(command, click.Group):
            yield from _walk_leaf_commands(command, path)
        else:
            yield path, command


class GlobalOptionGroup(click.Group):
    """Root group that lets global options appear anywhere on the command line.

    Click normally only parses group options before the subcommand. We reorder
    recognized global-option tokens to the front in :meth:`make_context`, so both
    `bidkit --dry-run sell ...` and `bidkit sell ... --dry-run` work, whether
    invoked via the console script or via :class:`click.testing.CliRunner`.
    """

    def make_context(self, info_name, args, **extra):  # type: ignore[override]
        return super().make_context(info_name, _reorder_global_options(list(args)), **extra)


def _global_options(func):
    """Attach the spec §8 global options to the root group callback."""
    options = [
        click.option("--config", "config_path", type=click.Path(), default=None,
                     help="Config file (default ~/.config/bidkit/config.json)."),
        click.option("--environment", type=click.Choice(["production", "sandbox"]),
                     default=None),
        click.option("--marketplace", default=None, help="Override marketplace ID."),
        click.option("--format", "output_format",
                     type=click.Choice(["json", "table", "text", "raw"]), default=None,
                     help="Output format (default: json when piped, table when a TTY)."),
        click.option("--pretty/--compact", "pretty", default=True,
                     help="Pretty-print JSON (default) or emit compact JSON."),
        click.option("--output-file", "output_file", type=click.Path(), default=None,
                     help="Save response body / binary output to a file."),
        click.option("--timeout", type=float, default=None,
                     help="Per-request timeout in seconds."),
        click.option("--max-retries", type=int, default=None, help="Retry override."),
        click.option("--log-level", type=click.Choice(LOG_LEVELS), default="warning"),
        click.option("--trace", is_flag=True, default=False,
                     help="Enable verbose transport diagnostics."),
        click.option("--no-color", is_flag=True, default=False),
        click.option("--allow-write", is_flag=True, default=False,
                     help="Permit operations classified as writes."),
        click.option("--allow-write-expert", is_flag=True, default=False,
                     help="Permit unclassified (unknown-risk) mutations. Expert only."),
        click.option("--yes", is_flag=True, default=False,
                     help="Skip confirmation for an already-permitted mutation."),
        click.option("--dry-run", is_flag=True, default=False,
                     help="Validate and print the request without sending it."),
        click.option("--select", default=None,
                     help="Project the output, e.g. --select item_summaries[].item_id."),
        click.option("--force", is_flag=True, default=False,
                     help="Allow overwriting an existing --output-file."),
        click.option("--include-meta", "include_meta", is_flag=True, default=False,
                     help="Wrap JSON output as {meta, data} with operation/status/request-id."),
        click.option("--content-language", "content_language", default=None,
                     help="Set the Content-Language header (e.g. de-DE) for EBAY_DE listings."),
        click.option("--marketplace-locale", "marketplace_locale", is_flag=True, default=False,
                     help="Derive Content/Accept-Language from --marketplace (EBAY_DE -> de-DE)."),
        click.option("--merge", "merge", is_flag=True, default=False,
                     help="Read-merge-write a replace-like PUT (updateOffer/createOrReplace)."),
        click.option("--verify-live", "verify_live", is_flag=True, default=False,
                     help="After a write, poll the API readback and report convergence."),
        click.option("--wait-for-live", "wait_for_live", type=float, default=0.0,
                     help="Seconds to wait for API readback during --verify-live."),
        # test-mode safety gate. Opt-in; only acts on the
        # description-carrying inventory/offer write ops.
        click.option("--test-mode", "test_mode", is_flag=True, default=False,
                     help="Require a test marker, scramble consent, and run-id "
                          "traceability for test listings (opt-in safety gate)."),
        click.option("--allow-scrambled-test-data", "allow_scrambled_test_data",
                     is_flag=True, default=False,
                     help="Consent to publishing cross-wired/scrambled test data "
                          "(requires --test-mode and --allow-write)."),
        click.option("--allow-untracked-test-run", "allow_untracked_test_run",
                     is_flag=True, default=False,
                     help="Expert override: allow a --test-run-id that is NOT "
                          "carried in the description/SKU (default: refused)."),
        click.option("--test-marker", "test_marker", default=None,
                     help="Test description marker (default: 'TEST ONLY')."),
        click.option("--test-run-id", "test_run_id", default=None,
                     help="Test run id to carry into description/SKU for traceability."),
        click.option("--test-provenance", "test_provenance", default=None,
                     help="JSON map of source SKUs per field, e.g. "
                          '{"title":"SKU_A","image":"SKU_B"}.'),
        click.option("--ledger-dir", "ledger_dir", default=None,
                     help="Directory for test-run ledger files (default: "
                          "$XDG_CACHE_HOME/bidkit/test-runs). Applies to both the "
                          "test-run commands and automatic event recording."),
    ]
    for option in reversed(options):
        func = option(func)
    return func


@click.group(
    cls=GlobalOptionGroup,
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 120},
    invoke_without_command=False,
)
@_global_options
@click.pass_context
def cli(ctx: click.Context, **kwargs: Any) -> None:
    """bidkit — every generated eBay operation, callable from the shell.

    Discover operations with `bidkit api list/search`, inspect one with
    `bidkit api describe`, then call it either directly
    (`bidkit sell inventory get-inventory-items`) or universally
    (`bidkit api call sell_inventory.getInventoryItems`).

    Mutating operations require --allow-write (and --yes for destructive ones).
    """
    context = CliContext(
        config_path=kwargs.get("config_path"),
        environment=kwargs.get("environment"),
        marketplace=kwargs.get("marketplace"),
        output_format=kwargs.get("output_format"),
        pretty=kwargs.get("pretty", True),
        output_file=kwargs.get("output_file"),
        timeout=kwargs.get("timeout"),
        max_retries=kwargs.get("max_retries"),
        log_level=kwargs.get("log_level", "warning"),
        trace=kwargs.get("trace", False),
        no_color=kwargs.get("no_color", False),
        allow_write=kwargs.get("allow_write", False),
        allow_write_expert=kwargs.get("allow_write_expert", False),
        yes=kwargs.get("yes", False),
        dry_run=kwargs.get("dry_run", False),
        select=kwargs.get("select"),
        force=kwargs.get("force", False),
        include_meta=kwargs.get("include_meta", False),
        content_language=kwargs.get("content_language"),
        accept_language=kwargs.get("accept_language"),
        marketplace_locale=kwargs.get("marketplace_locale", False),
        merge=kwargs.get("merge", False),
        verify_live=kwargs.get("verify_live", False),
        wait_for_live=kwargs.get("wait_for_live", 0.0),
        test_mode=kwargs.get("test_mode", False),
        allow_scrambled_test_data=kwargs.get("allow_scrambled_test_data", False),
        allow_untracked_test_run=kwargs.get("allow_untracked_test_run", False),
        test_marker=kwargs.get("test_marker"),
        test_run_id=kwargs.get("test_run_id"),
        test_provenance=_parse_test_provenance(kwargs.get("test_provenance")),
        ledger_dir=kwargs.get("ledger_dir"),
    )
    ctx.obj = context
    level = {"quiet": logging.CRITICAL, "warning": logging.WARNING,
             "info": logging.INFO, "debug": logging.DEBUG}[context.log_level]
    logging.getLogger("bidkit").setLevel(level)
    if context.trace:
        logging.getLogger("bidkit.transport").setLevel(logging.DEBUG)


def build_cli() -> click.Group:
    """Assemble the full command tree: static groups + generated namespace tree."""
    from .commands.api import api_group
    from .commands.auth import auth_group
    from .commands.capabilities import capabilities_group
    from .commands.config_cmd import config_group
    from .commands.generated import build_generated_groups
    from .commands.misc import completion_command, skill_command, version_command

    cli.add_command(api_group)
    cli.add_command(auth_group)
    cli.add_command(capabilities_group)
    cli.add_command(config_group)
    cli.add_command(version_command)
    cli.add_command(completion_command)
    cli.add_command(skill_command)

    # Generated namespace groups (buy, commerce, developer, post-order, sell).
    # Built lazily from the manifest so adding an operation upstream grows the
    # command tree automatically (spec §2.3).
    manifest = load_manifest()
    groups = build_generated_groups(manifest)
    # Layer hand-written workflow commands (sell inventory
    # verify-public, buy purchases capability) onto the generated tree so the
    # natural command path an agent guesses is available.
    from .commands.workflows import inject_workflow_commands

    inject_workflow_commands(groups)
    for group in groups:
        cli.add_command(group)
    # Fail fast with a clear compatibility error if the installed bidkit
    # generation differs from the one the manifest was generated against.
    assert_sdk_compatible(manifest)
    # Forbid leaf commands from declaring a global option name,
    # which the argv reorderer would silently consume before the command runs.
    _assert_no_global_option_collision(cli)
    return cli


# Build once at import so the console script (`bidkit`) and `python -m` share it.
build_cli()


def main() -> None:
    """Console-script entry point with structured error + exit-code handling.

    With ``standalone_mode=False`` Click converts a ``ctx.exit(n)``
    into a *return value* (``n``) rather than a ``SystemExit``, so the previous
    code that ignored ``cli.main``'s return value silently swallowed every
    intentional non-zero exit (e.g. ``verify-public`` on an unmet expectation).
    We now exit on that value, and also handle ``click.exceptions.Exit``
    defensively in case a future caller flips standalone mode back on.
    """
    reordered = _reorder_global_options(list(sys.argv[1:]))
    # The JSON-vs-text shape of an error follows the *requested* format, not
    # stdout's TTY-ness, so ``--format json`` on a TTY still emits a JSON error.
    # We parse the global --format from the reordered argv so
    # the decision is stable regardless of where the agent placed the flag.
    json_mode = _requested_json_mode(reordered)
    try:
        # standalone_mode=False lets us translate errors to our exit codes.
        rv = cli.main(args=reordered, standalone_mode=False, prog_name="bidkit")
    except click.exceptions.UsageError as exc:
        # Click usage errors join the stable error contract: the JSON envelope
        # in JSON mode (so `--format json` never gets bare prose), plain text
        # otherwise, exit 2 either way.
        ctx = exc.ctx
        if ctx and isinstance(ctx.obj, CliContext):
            json_mode = ctx.obj.json_mode
        from .errors import UsageError as _UsageError

        err = _UsageError(exc.format_message())
        sys.exit(report_error(err, json_mode=json_mode))
    except click.exceptions.Abort:
        # A user-aborted prompt (Ctrl-C at a confirmation) is distinct from a
        # safety *refusal*: 130 mirrors the shell convention for an interrupted
        # program, while a SafetyError keeps its dedicated exit 7.
        sys.exit(130)
    except click.exceptions.Exit as exc:
        sys.exit(exc.exit_code)
    except CliError as exc:
        sys.exit(report_error(exc, json_mode=json_mode))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        # Catch-all: any exception escaping the dispatch try (workflows, ledger,
        # streaming) is translated to a stable error instead of a raw traceback.
        # ``internal_error`` (exit 9) keeps a tool fault distinguishable from a
        # caller mistake (exit 2).
        from .errors import InternalError

        err = InternalError(
            f"unexpected error: {type(exc).__name__}: {exc}",
            hint="This is a bug in bidkit-cli, not in your request; "
                 "re-run with --log-level debug and report it.",
        )
        sys.exit(report_error(err, json_mode=json_mode))
    finally:
        # Close any client we opened. The context may live on the top Click ctx.
        _close_context()
    # Honor Click's intentional exit code (e.g. verify-public's 1).
    sys.exit(rv if isinstance(rv, int) else 0)


def _close_context() -> None:
    try:
        ctx = click.get_current_context(silent=True)
        if ctx and isinstance(ctx.obj, CliContext):
            ctx.obj.close()
    except Exception:  # noqa: BLE001 - cleanup must never mask the real exit
        pass


if __name__ == "__main__":
    main()
