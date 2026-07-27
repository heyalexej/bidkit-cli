"""Build the generated command tree from the manifest.

For every operation the manifest describes, produce a nested Click command:

    bidkit <namespace> <service> <operation>

Namespace ``post_order`` is exposed as ``post-order``. Operation names are
kebab-case; path params become positional arguments; query/header params become
repeatable options; JSON/multipart/binary bodies get the right option set.
"""

from __future__ import annotations

from typing import Any

import click

from ..context import CliContext
from ..dispatch import execute
from ..manifest import Manifest, OperationRecord, ParameterRecord
from ..parsing import (
    collect_header_params,
    collect_path_params,
    collect_query_params,
    parse_kv,
    read_body,
    read_multipart,
)


def build_generated_groups(manifest: Manifest) -> list[click.Group]:
    """One Click group per namespace, containing service groups containing ops."""
    groups: list[click.Group] = []
    for namespace in manifest.namespaces:
        cli_name = "post-order" if namespace == "post_order" else namespace
        operations = manifest.operations_for_namespace(namespace)
        if not operations:
            continue
        ns_group = click.Group(cli_name, help=f"Generated {namespace} API commands.")
        services_in_ns = sorted(
            {op.service_key for op in operations},
            key=lambda key: manifest.service(key).cli_name,
        )
        for service_key in services_in_ns:
            service = manifest.service(service_key)
            svc_ops = manifest.operations_for_service(service_key)
            # Manifest versions come in both "v1.2.3" and "1.2.3" forms.
            version = str(service.version)
            if not version.startswith("v"):
                version = f"v{version}"
            svc_group = click.Group(
                service.cli_name,
                help=f"{service.title} {version} — {len(svc_ops)} operation(s).",
            )
            for operation in svc_ops:
                svc_group.add_command(_operation_command(operation))
            ns_group.add_command(svc_group)
        groups.append(ns_group)
    return groups


def _operation_command(operation: OperationRecord) -> click.Command:
    params: list[click.Parameter] = []
    # dest -> ParameterRecord for every path/query/header param we declare, so
    # run_operation can bucket values by location and wire name without guessing
    # from Click's normalized kwarg names. Two naming traps forced this:
    #   * path args: Click normalizes the cli name ``order-id`` into the Python
    #     keyword ``order_id``, which never matched the camelCase wire name
    #     ``orderId``.
    #   * header wire names carry hyphens (``Accept-Language``,
    #     ``X-EBAY-C-ENDUSERCTX``) and are not valid Python identifiers, so Click
    #     rejected them as option destinations.
    dest_map: dict[str, ParameterRecord] = {}

    def add(param: ParameterRecord, *, positional: bool) -> None:
        dest = _make_dest(param, dest_map)
        dest_map[dest] = param
        if positional:
            # Path args are optional at the Click layer: a universal --path
            # override can satisfy one without a dummy positional value, and
            # collect_path_params re-checks the required ones.
            params.append(
                click.Argument([dest], required=False, metavar=param.cli_name.upper())
            )
        else:
            # An operation can legitimately declare a query/header param whose
            # name matches a global option (e.g. sell_inventory.getOffers has a
            # ``format`` query param). The argv
            # reorderer would hoist ``--format`` to the root and the value would
            # never reach this param, so we expose a location-prefixed option
            # (``--q-format``/``--h-format``) and point the help at the universal
            # ``--query``/``--header`` form.
            opt_name = _option_name(param)
            params.append(
                click.Option(
                    [f"--{opt_name}", dest],
                    multiple=param.is_array,
                    default=None,
                    help=_param_help(param),
                )
            )

    for param in operation.path_params:
        add(param, positional=True)
    for param in operation.query_params + operation.header_params:
        add(param, positional=False)

    # Request body options depend on kind.
    params.extend(_body_params(operation))
    params.extend(_universal_options())

    @click.command(operation.cli_name, params=params, help=_help_text(operation))
    @click.pass_context
    def _cmd(ctx: click.Context, **kwargs: Any) -> None:
        context: CliContext = ctx.obj
        run_operation(context, operation, kwargs, dest_map)

    return _cmd


def _universal_options() -> list[click.Parameter]:
    """The repeatable --query / --header / --path escape hatches."""
    return [
        click.Option(["--query", "universal_query"], multiple=True,
                     help="Query param as NAME=VALUE (repeatable)."),
        click.Option(["--header", "universal_header"], multiple=True,
                     help="Header as NAME=VALUE (repeatable)."),
        click.Option(["--path", "universal_path"], multiple=True,
                     help="Path param as NAME=VALUE (the universal form)."),
        click.Option(["--allow-unknown-params"], is_flag=True, default=False,
                     help="Accept parameters not in the manifest (experimental)."),
    ]


def _option_name(param: ParameterRecord) -> str:
    """The user-facing option name for a query/header param.

    A param whose ``--cli_name`` matches a global option is prefixed by location
    (``q-`` for query, ``h-`` for header) so the argv reorderer does not steal
    it. The wire name is unaffected; only the CLI spelling changes.
    """
    from ..app import _ALL_GLOBAL_OPTION_NAMES

    if f"--{param.cli_name}" in _ALL_GLOBAL_OPTION_NAMES:
        prefix = "h-" if param.location == "header" else "q-"
        return f"{prefix}{param.cli_name}"
    return param.cli_name


def _make_dest(param: ParameterRecord, taken: dict[str, Any]) -> str:
    """A stable, identifier-safe Click destination unique within the command."""
    base = f"_p_{param.location}_{_slug(param.wire_name)}"
    dest, n = base, 2
    while dest in taken:
        dest = f"{base}_{n}"
        n += 1
    return dest


def _slug(name: str) -> str:
    """Identifier-safe, lower-cased slug.

    Lower-casing matters: Click lower-cases *argument* parameter names but
    preserves *option* destinations verbatim, so a camelCase wire name
    (``orderId``) would otherwise land under different keys depending on whether
    the param is positional. The dedupe suffix in :func:`_make_dest` keeps the
    result unique even if two wire names collide once lower-cased.
    """
    import re

    slug = re.sub(r"[^0-9A-Za-z]", "_", name).lower()
    return slug or "_"


def _param_help(param: ParameterRecord) -> str:
    help_text = param.description or param.wire_name
    if param.required:
        help_text = f"[required] {help_text}"
    if param.enum:
        sample = ", ".join(str(v) for v in param.enum[:6])
        help_text += f" (enum: {sample}{' ...' if len(param.enum) > 6 else ''})"
    return help_text


def _body_params(operation: OperationRecord) -> list[click.Parameter]:
    kind = operation.request.kind
    if kind == "json":
        return [
            click.Option(["--body", "body_arg"], default=None,
                         help="Request body: @file.json, @- for stdin, or inline JSON."),
            click.Option(["--body-json"], default=None, help="Inline JSON request body."),
        ]
    if kind == "multipart":
        file_fields = [f.name for f in operation.request.fields if f.kind == "file"]
        return [
            click.Option(["--file", "file_pairs"], multiple=True,
                         help="Multipart file as NAME=@PATH (repeatable). "
                              f"Files: {', '.join(file_fields) or '(none)'}"),
            click.Option(["--field", "field_pairs"], multiple=True,
                         help="Multipart text field as NAME=VALUE (repeatable)."),
        ]
    if kind == "binary":
        return [
            click.Option(["--body-file", "body_file"], default=None,
                         help="Path to a binary request body file."),
        ]
    return []


def run_operation(
    context: CliContext,
    operation: OperationRecord,
    kwargs: dict[str, Any],
    dest_map: dict[str, ParameterRecord],
) -> None:
    """Collect parsed Click kwargs into dispatch inputs and execute.

    Named path/query/header options are bucketed by location using ``dest_map``
    so header values reach the header collection and positional
    path values bind by declared order regardless of camelCase wire names.
    """
    universal_query = [parse_kv(v, kind="query") for v in kwargs.pop("universal_query", ())]
    universal_header = [parse_kv(v, kind="header") for v in kwargs.pop("universal_header", ())]
    universal_path = [parse_kv(v, kind="path") for v in kwargs.pop("universal_path", ())]
    allow_unknown = kwargs.pop("allow_unknown_params", False)

    # Body options are stored under fixed dests that never collide with params.
    body_arg = kwargs.pop("body_arg", None)
    body_json = kwargs.pop("body_json", None)
    body_file = kwargs.pop("body_file", None)
    file_pairs = [parse_kv(v, kind="file") for v in kwargs.pop("file_pairs", ())]
    field_pairs = [parse_kv(v, kind="field") for v in kwargs.pop("field_pairs", ())]

    # Remaining kwargs are the named path/query/header options keyed by dest.
    dest_by_param = {(p.location, p.wire_name): d for d, p in dest_map.items()}
    provided: dict[str, list[str]] = {}
    for dest, value in kwargs.items():
        if value is None or dest not in dest_map:
            continue
        provided[dest] = (
            [str(v) for v in value] if isinstance(value, tuple) else [str(value)]
        )

    # Path values in declared parameter order (dict iteration is unordered).
    positional: list[str] = []
    for param in operation.path_params:
        values = provided.pop(dest_by_param[("path", param.wire_name)], None)
        if values:
            positional.append(values[0])

    # Split the remaining named options by location: query vs header.
    query_explicit: dict[str, list[str]] = {}
    header_explicit: dict[str, list[str]] = {}
    for dest, values in provided.items():
        param = dest_map[dest]
        bucket = header_explicit if param.location == "header" else query_explicit
        bucket[param.wire_name] = values

    path_params = collect_path_params(
        operation, positional=positional, universal=universal_path
    )
    query_params = collect_query_params(
        operation,
        explicit=query_explicit,
        universal=universal_query,
        allow_unknown=allow_unknown,
    )
    header_params = collect_header_params(
        operation,
        explicit=header_explicit,
        universal=universal_header,
        allow_unknown=allow_unknown,
    )

    body = read_body(body_arg=body_arg, body_json=body_json, body_file=body_file)
    files = read_multipart(file_pairs=file_pairs, field_pairs=field_pairs)

    execute(
        context,
        operation,
        path_params=path_params,
        query_params=query_params,
        header_params=header_params,
        body=body,
        files=files,
    )


def _help_text(operation: OperationRecord) -> str:
    """A compact, agent-friendly help block.

    Answers the first execution questions without a second command: canonical
    key, HTTP method/path, effective risk, scopes, request/response shape, and a
    ready-to-run example. Full OAS prose stays in ``api describe``.

    Structured blocks are prefixed with ``\b`` so Click renders them verbatim
    instead of reflowing ``HTTP``/``Risk``/``Scopes`` into an unreadable wrapped
    paragraph; the summary line is left to wrap normally.
    """
    from ..safety import effective_risk

    risk, reason = effective_risk(operation)
    summary = (operation.summary or operation.key).strip().splitlines()[0]

    # Build the structured (verbatim) blocks, then join each with a ``\b`` guard.
    meta: list[str] = [f"Operation: {operation.key}"]
    meta.append(f"HTTP: {operation.http_method} {operation.path}")
    meta.append(f"Risk: {risk.upper()}")
    if reason and risk == "unknown":
        meta.append(f"Risk note: {reason}")

    # Scopes — the exact OAuth scopes this call needs.
    if operation.auth.scopes:
        if len(operation.auth.scopes) == 1:
            meta.append(f"Scope: {operation.auth.scopes[0]}")
        else:
            meta.append("Scopes:")
            for scope in operation.auth.scopes:
                meta.append(f"  {scope}")

    # Request shape (required inputs first, then kind).
    required_inputs = _required_inputs(operation)
    if required_inputs:
        meta.append("Required inputs: " + ", ".join(required_inputs))
    meta.append("Request: none" if operation.request.kind == "none"
               else f"Request: {operation.request.kind}")

    # Replace-like PUTs revert omitted fields to defaults; surface the risk and
    # the --merge read/merge/write wrapper in help.
    from ..workflows import is_replace_like

    if is_replace_like(operation):
        meta.append(
            "Replace-like: the body is a full replacement. Use --merge to "
            "read-merge-write (omitted fields are preserved, not defaulted)."
        )

    # Successful response media types + statuses. A generated operation can
    # return several success statuses with different bodies (updateOffer returns
    # 200 JSON *or* 204 No Content); render all of them so an agent's
    # expectation about whether a response body exists matches reality.
    successes = operation.success_responses
    if successes:
        meta.append("Success: " + "; ".join(_render_success(r) for r in successes))
    else:
        meta.append("Response: (none)")

    if operation.signing.required:
        meta.append("Requires digital signature (configured via signing key).")

    blocks: list[str] = ["\n".join(meta)]

    # One ready-to-run example (prefer a safe one).
    examples = operation.examples
    safe = next((e for e in examples if e.safe), examples[0] if examples else None)
    if safe is not None:
        example_lines = ["Example:", f"  {safe.command}"]
        if safe.note:
            example_lines.append(f"  # {safe.note}")
        more = len(examples) - 1
        if more > 0:
            example_lines.append(f"  # {more} more: `bidkit api examples {operation.key}`")
        blocks.append("\n".join(example_lines))

    blocks.append(
        "Global options are accepted before or after the command:\n"
        "  --format json   --dry-run   --select PATH   --output-file PATH"
    )
    blocks.append(f"Direct command: bidkit {' '.join(operation.cli_path)}")

    verbatim = "\n\n".join("\b\n" + block for block in blocks)
    return f"{summary}\n\n{verbatim}"


def _render_success(response) -> str:
    """One success descriptor for help, e.g. ``200 application/json`` / ``204 No Content``.

    An empty body (kind ``none``) is labeled ``No Content`` so a 204 is visibly a
    terminal success with no payload, instead of the misleading ``none`` kind.
    """
    media = response.content_type or (response.kind if response.kind != "none" else None)
    if media is None:
        return f"{response.status} No Content"
    return f"{response.status} {media}"


def _required_inputs(operation: OperationRecord) -> list[str]:
    """Required path/query/header names, shown before optional inputs."""
    inputs: list[str] = []
    inputs.extend(p.cli_name for p in operation.path_params if p.required)
    inputs.extend(f"--{_option_name(p)}" for p in operation.query_params if p.required)
    inputs.extend(f"--{_option_name(p)}" for p in operation.header_params if p.required)
    return inputs
