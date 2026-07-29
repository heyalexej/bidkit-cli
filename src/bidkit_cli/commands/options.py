"""Shared Click option specs for request escape hatches and polling.

Two option surfaces are centralized here so each is declared once and reused
across the commands that need it:

* the **request escape-hatch options** — ``--query``/``--header``/``--path``/
  ``--allow-unknown-params`` plus the body options ``--body``/``--body-json``/
  ``--body-file``/``--file``/``--field`` — described by one spec table
  (``_REQUEST_OPTION_SPECS``) and built fresh on every call. ``api call`` and
  every generated operation command draw from the same source of truth, so the
  universal override surface is identical everywhere it appears;
* :func:`public_poll_options`, a decorator factory adding the ``--wait``/
  ``--poll`` polling pair consumed by the long-poll workflow commands.

A Click :class:`click.Option` is mutable and binds to a single command when
parsed, so the factories below never hand out a shared instance — each call
builds a brand-new one. Per-operation help (e.g. the multipart file-field list)
is layered on by the caller through the factories' hooks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import click


@dataclass(frozen=True)
class _RequestOptionSpec:
    """Declarative spec for one request escape-hatch option.

    The single source of truth for an option's Click spelling (``decls``),
    destination, multiplicity, and help. The factories below read a spec and
    build a fresh ``click.Option`` from it, so no two commands ever share a
    mutable parameter.
    """

    decls: tuple[str, ...]
    multiple: bool = False
    is_flag: bool = False
    default: Any = None
    help: str = ""


# One declaration per escape-hatch option. The destination is pinned explicitly
# (the second token of ``decls`` where present) so ``run_operation`` can pop each
# value by the same fixed name whether it arrived via ``api call`` or a generated
# command. ``--allow-unknown-params`` has no explicit destination because its
# auto-derived one (``allow_unknown_params``) is already the name the runner pops.
_REQUEST_OPTION_SPECS: dict[str, _RequestOptionSpec] = {
    "query": _RequestOptionSpec(
        decls=("--query", "universal_query"),
        multiple=True,
        help="Query param as NAME=VALUE (repeatable).",
    ),
    "header": _RequestOptionSpec(
        decls=("--header", "universal_header"),
        multiple=True,
        help="Header as NAME=VALUE (repeatable).",
    ),
    "path": _RequestOptionSpec(
        decls=("--path", "universal_path"),
        multiple=True,
        help="Path param as NAME=VALUE (the universal form).",
    ),
    "allow_unknown_params": _RequestOptionSpec(
        decls=("--allow-unknown-params",),
        is_flag=True,
        default=False,
        help="Accept parameters not in the manifest (experimental).",
    ),
    "body": _RequestOptionSpec(
        decls=("--body", "body_arg"),
        help="Request body: @file.json, @- for stdin, or inline JSON.",
    ),
    "body_json": _RequestOptionSpec(
        decls=("--body-json", "body_json"),
        help="Inline JSON request body.",
    ),
    "body_file": _RequestOptionSpec(
        decls=("--body-file", "body_file"),
        help="Path to a binary request body file.",
    ),
    "file": _RequestOptionSpec(
        decls=("--file", "file_pairs"),
        multiple=True,
        help="Multipart file as NAME=@PATH (repeatable).",
    ),
    "field": _RequestOptionSpec(
        decls=("--field", "field_pairs"),
        multiple=True,
        help="Multipart text field as NAME=VALUE (repeatable).",
    ),
}


def _build_option(spec: _RequestOptionSpec, *, help: str | None = None) -> click.Option:
    """Build a fresh ``click.Option`` from ``spec``.

    A new instance on every call is load-bearing: a Click ``Option`` carries
    per-command parse state, and reusing one across commands would let a later
    command's parsing corrupt an earlier one's defaults. ``help`` overrides the
    spec's text so callers can layer on per-operation detail (the multipart
    file-field list) without forking the spec.
    """
    return click.Option(
        list(spec.decls),
        multiple=spec.multiple,
        is_flag=spec.is_flag,
        default=spec.default,
        help=help if help is not None else spec.help,
    )


# --- individual fresh constructors -----------------------------------------


def make_query_option() -> click.Option:
    """A fresh ``--query`` (``universal_query``, repeatable) option."""
    return _build_option(_REQUEST_OPTION_SPECS["query"])


def make_header_option() -> click.Option:
    """A fresh ``--header`` (``universal_header``, repeatable) option."""
    return _build_option(_REQUEST_OPTION_SPECS["header"])


def make_path_option() -> click.Option:
    """A fresh ``--path`` (``universal_path``, repeatable) option."""
    return _build_option(_REQUEST_OPTION_SPECS["path"])


def make_allow_unknown_params_option() -> click.Option:
    """A fresh ``--allow-unknown-params`` flag (``allow_unknown_params``)."""
    return _build_option(_REQUEST_OPTION_SPECS["allow_unknown_params"])


def make_body_option() -> click.Option:
    """A fresh ``--body`` (``body_arg``) option."""
    return _build_option(_REQUEST_OPTION_SPECS["body"])


def make_body_json_option() -> click.Option:
    """A fresh ``--body-json`` (``body_json``) option."""
    return _build_option(_REQUEST_OPTION_SPECS["body_json"])


def make_body_file_option() -> click.Option:
    """A fresh ``--body-file`` (``body_file``) option."""
    return _build_option(_REQUEST_OPTION_SPECS["body_file"])


def make_file_option(*, help: str | None = None) -> click.Option:
    """A fresh ``--file`` (``file_pairs``, repeatable) multipart option."""
    return _build_option(_REQUEST_OPTION_SPECS["file"], help=help)


def make_field_option() -> click.Option:
    """A fresh ``--field`` (``field_pairs``, repeatable) multipart option."""
    return _build_option(_REQUEST_OPTION_SPECS["field"])


# --- composite constructors -------------------------------------------------


def make_universal_options() -> list[click.Option]:
    """The repeatable escape hatches plus ``--allow-unknown-params``.

    Identical on ``api call`` and every generated operation, so the universal
    override surface is the same wherever an agent reaches for it. Order is part
    of the contract — ``--query``, ``--header``, ``--path``, then
    ``--allow-unknown-params`` — and matches the historical help ordering.
    """
    return [
        make_query_option(),
        make_header_option(),
        make_path_option(),
        make_allow_unknown_params_option(),
    ]


def make_all_body_options() -> list[click.Option]:
    """Every body option at once — ``api call`` accepts any request kind.

    The generated commands expose only the body options their request kind
    allows (see :func:`make_body_options_for_kind`); ``api call`` is universal,
    so it offers the union and lets the runner pick the relevant one.
    """
    return [
        make_body_option(),
        make_body_json_option(),
        make_body_file_option(),
        make_file_option(),
        make_field_option(),
    ]


def make_body_options_for_kind(
    kind: str, *, file_fields: list[str] | None = None
) -> list[click.Option]:
    """Body options for a generated command's request kind.

    Mirrors the per-kind surface the manifest describes: JSON bodies get
    ``--body``/``--body-json``, multipart gets ``--file``/``--field`` (with the
    operation's known file fields named in ``--file``'s help), binary gets
    ``--body-file``, and an empty body gets nothing. An unrecognized kind yields
    nothing rather than a misleading option set.
    """
    if kind == "json":
        return [make_body_option(), make_body_json_option()]
    if kind == "multipart":
        fields = list(file_fields or [])
        listed = ", ".join(fields) if fields else "(none)"
        file_help = f"{_REQUEST_OPTION_SPECS['file'].help} Files: {listed}"
        return [make_file_option(help=file_help), make_field_option()]
    if kind == "binary":
        return [make_body_file_option()]
    return []


# --- polling options (consumed by the workflow commands) -------------------


def public_poll_options() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator factory attaching the ``--wait``/``--poll`` polling pair.

    ``--wait`` (a :class:`click.FloatRange` with ``min=0``, default ``0``) bounds
    the total seconds to wait for an expected state — ``0`` means a single
    check. ``--poll`` (a strictly positive ``FloatRange``, default ``15``) sets
    the seconds between checks. Destinations are pinned to ``wait_seconds`` and
    ``poll_interval`` so workflow callbacks read them under those names, and
    ``show_default`` documents both defaults in ``--help``.

    Used as a decorator on a command callback::

        @click.command()
        @public_poll_options()
        def cmd(ctx, wait_seconds, poll_interval): ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        # Click reverses ``__click_params__`` when finalizing a command, so to
        # render ``--wait`` above ``--poll`` in --help the option applied LAST
        # is ``--wait``. Apply ``--poll`` first, then ``--wait``.
        func = click.option(
            "--poll",
            "poll_interval",
            type=click.FloatRange(min=0, min_open=True),
            default=15.0,
            show_default=True,
            help="Seconds between polls (must be greater than 0).",
        )(func)
        func = click.option(
            "--wait",
            "wait_seconds",
            type=click.FloatRange(min=0),
            default=0.0,
            show_default=True,
            help="Seconds to wait for the expected state (0 means a single check).",
        )(func)
        return func

    return decorator
