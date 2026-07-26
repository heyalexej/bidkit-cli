"""``bidkit version`` and ``bidkit completion`` commands (spec §7.1, §15.4)."""

from __future__ import annotations

import click

from .. import __version__
from ..rendering import emit_json


@click.command("version", help="Print CLI and SDK versions.")
@click.pass_context
def version_command(ctx: click.Context) -> None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        sdk_version = version("bidkit")
    except PackageNotFoundError:
        sdk_version = "unknown"
    from ..context import CliContext

    context: CliContext = ctx.obj
    payload = {"cli": __version__, "sdk": sdk_version, "executable": "bidkit"}
    emit_json(payload, pretty=context.pretty)


@click.command("completion", help="Generate shell completion scripts (zsh/bash/fish).")
@click.argument("shell", type=click.Choice(["zsh", "bash", "fish"]), required=True)
@click.option(
    "--install",
    is_flag=True,
    default=False,
    help="Print install instructions instead of the script (best effort).",
)
def completion_command(shell: str, install: bool) -> None:
    """Emit a shell completion script. Requires no network access.

    Completion is Click-builtin; it covers namespaces, services, operations,
    and option names. (Enum completion is wired through Click's choices.)
    """
    env_var = "_BIDKIT_COMPLETE"
    if shell == "zsh":
        script = f"""# {shell} completion for bidkit
eval "$({env_var}=zsh_source bidkit)"
"""
    elif shell == "bash":
        script = f"""# {shell} completion for bidkit
eval "$({env_var}=bash_source bidkit)"
"""
    else:
        script = f"""# {shell} completion for bidkit
{env_var}=fish_source bidkit | source
"""
    if install:
        click.echo(f"# Add this to your ~/.{shell}rc or the appropriate rc file:")
    click.echo(script)


@click.command("skill", help="Print the location of the packaged agent skill.")
@click.pass_context
def skill_command(ctx: click.Context) -> None:
    """Resolve and print the installed SKILL.md path.

    The progressive-disclosure skill is packaged inside the wheel under
    ``bidkit_cli/skill/``. An agent runtime loads SKILL.md from here; if the
    package was installed without the skill data, this reports that clearly
    instead of implying pip installed it.
    """
    from importlib import resources
    from pathlib import Path

    from ..context import CliContext

    context: CliContext = ctx.obj
    try:
        skill_md = resources.files("bidkit_cli").joinpath("skill").joinpath("SKILL.md")
        path = Path(str(skill_md))
    except (ModuleNotFoundError, FileNotFoundError):
        path = None
    if path and path.exists():
        click.echo(str(path))
    else:
        click.echo(
            "skill is not packaged in this install; see the repository at "
            "skills/bidkit-cli/SKILL.md"
        )
    _ = context  # context available for future JSON output of the path
