"""``bidkit api`` — universal operation discovery and dispatch (spec §7.3).

list / search / describe / schema work offline (no client, no token, no network).
call is the stable universal dispatcher that direct commands are built on top of.
"""

from __future__ import annotations

from typing import Any

import click

from ..context import CliContext
from ..errors import UsageError
from ..manifest import AmbiguousOperation, Manifest, OperationRecord
from ..rendering import emit_json
from .generated import run_operation

DESC_KINDS = {"describe", "schema"}


@click.group("api", help="Search, describe, inspect schemas, and invoke generated operations.")
def api_group() -> None:
    pass


@api_group.command("list")
@click.option("--namespace", default=None, help="Filter by namespace (e.g. sell).")
@click.option("--service", default=None, help="Filter by service key (e.g. sell_inventory).")
@click.option("--tag", default=None, help="Filter by tag.")
@click.option("--method", default=None, help="Filter by HTTP method.")
@click.option("--domain", default=None,
              help="Filter by data domain (seller_sales/guest_checkout/feedback).")
@click.pass_context
def api_list(
    ctx: click.Context,
    namespace: str | None,
    service: str | None,
    tag: str | None,
    method: str | None,
    domain: str | None,
) -> None:
    """List services or operations."""
    context: CliContext = ctx.obj
    manifest = context.manifest
    operations = list(manifest.operations)
    if namespace:
        operations = [op for op in operations if op.namespace == _resolve_namespace(namespace)]
    if service:
        operations = [op for op in operations if op.service_key == service]
    if tag:
        operations = [op for op in operations if tag in op.tags]
    if method:
        operations = [op for op in operations if op.http_method.upper() == method.upper()]
    if domain:
        operations = [op for op in operations if _domain(op) == domain]

    # --format is a global option (hoisted by the argv
    # reorderer), so read it from the context instead of a dead local flag.
    use_json = context.effective_format == "json"
    if use_json:
        # service_count reflects the *filtered* result: the set
        # of services touched by the returned operations, not the global manifest
        # total. The global totals are preserved under ``manifest`` so an agent
        # never has to infer which counts are filtered.
        filtered_service_keys = {op.service_key for op in operations}
        payload = {
            "service_count": len(filtered_service_keys),
            "operation_count": len(operations),
            "manifest": {
                "service_count": len(manifest.services),
                "operation_count": len(manifest.operations),
            },
            "operations": [_op_summary(op) for op in operations],
        }
        emit_json(payload, pretty=context.pretty)
    else:
        _print_operation_table(operations)


@api_group.command("search")
@click.argument("query", required=False)
@click.option("--method", default=None, help="Filter by HTTP method.")
@click.option("--tag", default=None)
@click.option("--domain", default=None,
              help="Filter by data domain (seller_sales/guest_checkout/feedback).")
@click.pass_context
def api_search(
    ctx: click.Context,
    query: str | None,
    method: str | None,
    tag: str | None,
    domain: str | None,
) -> None:
    """Search operation ids, service names, tags, summaries, and paths."""
    context: CliContext = ctx.obj
    manifest = context.manifest
    operations = manifest.search(query) if query else list(manifest.operations)
    if method:
        operations = [op for op in operations if op.http_method.upper() == method.upper()]
    if tag:
        operations = [op for op in operations if tag in op.tags]
    if domain:
        operations = [op for op in operations if _domain(op) == domain]
    use_json = context.effective_format == "json"
    if use_json:
        emit_json(
            {"query": query, "count": len(operations),
             "operations": [_op_summary(op) for op in operations]},
            pretty=context.pretty,
        )
    else:
        _print_operation_table(operations)


@api_group.command("describe")
@click.argument("operation", required=True)
@click.pass_context
def api_describe(ctx: click.Context, operation: str) -> None:
    """Show complete operation metadata without making a network request."""
    context: CliContext = ctx.obj
    record = _resolve(context.manifest, operation)
    emit_json(_describe_payload(record, context.manifest), pretty=context.pretty)


@api_group.command("examples")
@click.argument("operation", required=True)
@click.pass_context
def api_examples(
    ctx: click.Context, operation: str
) -> None:
    """Print copy-pasteable example commands for an operation (offline).

    Every operation has at least one safe example (a real call for reads, a
    --dry-run preview for writes) plus, where applicable, an execute example
    carrying the exact safety gates the operation requires.
    """
    context: CliContext = ctx.obj
    record = _resolve(context.manifest, operation)
    examples = record.examples
    use_json = context.effective_format == "json"
    if use_json:
        emit_json(
            {
                "operation": record.key,
                "examples": [e.model_dump() for e in examples],
            },
            pretty=context.pretty,
        )
    else:
        click.echo(f"# {record.key}")
        for ex in examples:
            tag = "safe" if ex.safe else "execute"
            click.echo(f"# [{tag}] {ex.command}")
            if ex.note:
                click.echo(f"#   {ex.note}")


@api_group.command("schema")
@click.argument("operation", required=True)
@click.argument("target", type=click.Choice(["request", "response"]), required=True)
@click.option("--model", default=None, help="Inspect a specific model by name.")
@click.pass_context
def api_schema(
    ctx: click.Context, operation: str, target: str, model: str | None
) -> None:
    """Print the Pydantic/OpenAPI-derived JSON Schema for a request or response.

    Works offline for modeled requests/responses: the schema comes from the
    generated Pydantic model's ``model_json_schema()``, not from shipping the OAS.
    Enum and other non-Pydantic classes named via ``--model`` are emitted as a
    valid enum schema or rejected with a structured error.
    """
    context: CliContext = ctx.obj
    record = _resolve(context.manifest, operation)
    model_cls = _resolve_schema_model(record, target, model)
    if model_cls is None:
        raise UsageError(
            f"{record.key} has no modeled {target}; it is untyped."
        )
    schema = _schema_for_class(model_cls)
    emit_json(schema, pretty=context.pretty)


@api_group.command("call")
@click.argument("service", required=True)
@click.argument("operation", required=False)
@click.option("--query", "universal_query", multiple=True, help="NAME=VALUE (repeatable).")
@click.option("--header", "universal_header", multiple=True, help="NAME=VALUE (repeatable).")
@click.option("--path", "universal_path", multiple=True, help="NAME=VALUE (repeatable).")
@click.option("--body", "body_arg", default=None, help="@file | @- | inline JSON.")
@click.option("--body-json", default=None, help="Inline JSON request body.")
@click.option("--body-file", default=None, help="Binary body file path.")
@click.option("--file", "file_pairs", multiple=True, help="NAME=@PATH (multipart).")
@click.option("--field", "field_pairs", multiple=True, help="NAME=VALUE (multipart).")
@click.option("--allow-unknown-params", is_flag=True, default=False)
@click.pass_context
def api_call(
    ctx: click.Context,
    service: str,
    operation: str | None,
    universal_query: tuple[str, ...],
    universal_header: tuple[str, ...],
    universal_path: tuple[str, ...],
    body_arg: str | None,
    body_json: str | None,
    body_file: str | None,
    file_pairs: tuple[str, ...],
    field_pairs: tuple[str, ...],
    allow_unknown_params: bool,
) -> None:
    """Invoke any manifest operation by canonical key or aliases.

    \b
    Examples:
      bidkit api call sell_inventory.getInventoryItems --query limit=20
      bidkit api call sell_inventory getInventoryItems --query limit=20
    """
    context: CliContext = ctx.obj
    # ``service`` may be the full canonical key (with a dot) when operation is
    # not supplied, or a service key when operation is supplied.
    if operation is None:
        record = _resolve(context.manifest, service)
    else:
        record = _resolve(context.manifest, service, operation_id=operation)

    kwargs = _collect_call_kwargs(
        record,
        universal_query=universal_query,
        universal_header=universal_header,
        universal_path=universal_path,
        body_arg=body_arg,
        body_json=body_json,
        body_file=body_file,
        file_pairs=file_pairs,
        field_pairs=field_pairs,
        allow_unknown_params=allow_unknown_params,
    )
    run_operation(context, record, kwargs, dest_map={})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_namespace(value: str) -> str:
    return "post_order" if value == "post-order" else value


def _resolve(
    manifest: Manifest, identifier: str, *, operation_id: str | None = None
) -> OperationRecord:
    """Resolve for describe/schema (display) — allows bare ambiguous matches too
    by picking the single match, but never silently dispatches an ambiguous id."""
    try:
        if operation_id is not None:
            return manifest.resolve(operation_id, service=identifier)
        return manifest.resolve(identifier)
    except AmbiguousOperation as exc:
        raise UsageError(str(exc)) from exc
    except LookupError as exc:
        raise UsageError(str(exc)) from exc


def _resolve_schema_model(
    record: OperationRecord, target: str, model_name: str | None
) -> Any:
    if model_name:
        # Explicit model inspection: resolve within the service's module.
        service_module = f"bidkit.generated.models.{record.service_key}"
        import importlib

        module = importlib.import_module(service_module)
        cls = getattr(module, model_name, None)
        if cls is None:
            raise UsageError(f"model {model_name!r} not found in {service_module}")
        return cls
    if target == "request":
        return record.request.model_ref.import_class()
    # An operation may declare a 204 No Content *before* a modeled 200; pick
    # the first JSON success that actually has a model so the schema is the real
    # response shape, not an empty no-content body.
    for response in record.success_responses:
        if response.kind == "json" and response.model:
            return response.model_ref.import_class()
    return None


def _schema_for_class(cls: Any) -> dict[str, Any]:
    """Emit a JSON Schema for a Pydantic model, an Enum, or raise.

    A bare ``--model ConditionEnum`` previously crashed with AttributeError
    because enums (and other generated non-Pydantic classes) have no
    ``model_json_schema``. Enums now produce a valid ``{"type": ..., "enum": ...}``
    schema; anything else surfaces a structured usage error naming the accepted
    kinds so the caller knows what to pass.
    """
    import enum

    from pydantic import BaseModel

    if isinstance(cls, type) and issubclass(cls, BaseModel):
        return cls.model_json_schema(
            by_alias=True, ref_template="#/components/schemas/{model}"
        )
    if isinstance(cls, type) and issubclass(cls, enum.Enum):
        # Values may be str/int; OpenAPI wants a single primitive type.
        values = [member.value for member in cls]
        schema_type = (
            "integer" if all(isinstance(v, int) and not isinstance(v, bool) for v in values)
            else "string"
        )
        return {"title": cls.__name__, "type": schema_type, "enum": values}
    raise UsageError(
        f"{getattr(cls, '__name__', cls)!r} is not a Pydantic model or enum and "
        "has no JSON Schema; pass a generated model (BaseModel) or enum class "
        "name to --model."
    )


def _describe_payload(record: OperationRecord, manifest: Manifest) -> dict[str, Any]:
    service = manifest.service(record.service_key)
    return {
        "key": record.key,
        "operation_id": record.operation_id,
        "python_method": record.python_method,
        "aliases": record.aliases,
        "cli_command": " ".join(record.cli_path),
        "http_method": record.http_method,
        "path": record.path,
        "summary": record.summary,
        "tags": record.tags,
        "service": {
            "key": service.key,
            "title": service.title,
            "version": service.version,
            "base_path": service.base_path,
            "subdomain": service.subdomain,
            "auth_scheme": service.auth_scheme,
            "requires_signature": service.requires_signature,
        },
        "auth": record.auth.model_dump(),
        "signing": record.signing.model_dump(),
        "risk": record.risk,
        "effective_risk": _effective(record),
        "domain": _domain(record),
        "replace_like": _is_replace_like(record),
        "request": record.request.model_dump(),
        "parameters": [p.model_dump() for p in record.parameters],
        "responses": [r.model_dump() for r in record.responses],
        "stream_method": record.stream_method,
        "examples": [e.model_dump() for e in record.examples],
        "schema_command": (
            f"bidkit api schema {record.key} request"
            if record.request.model
            else None
        ),
    }


def _collect_call_kwargs(
    record: OperationRecord,
    *,
    universal_query: tuple[str, ...],
    universal_header: tuple[str, ...],
    universal_path: tuple[str, ...],
    body_arg: str | None,
    body_json: str | None,
    body_file: str | None,
    file_pairs: tuple[str, ...],
    field_pairs: tuple[str, ...],
    allow_unknown_params: bool,
) -> dict[str, Any]:
    """For api call, all params come via universal --query/--header/--path.

    We stage them as Click-style kwargs the generated runner understands.
    """
    kwargs: dict[str, Any] = {
        "universal_query": universal_query,
        "universal_header": universal_header,
        "universal_path": universal_path,
        "body_arg": body_arg,
        "body_json": body_json,
        "body_file": body_file,
        "file_pairs": file_pairs,
        "field_pairs": field_pairs,
        "allow_unknown_params": allow_unknown_params,
    }
    return kwargs


def _op_summary(op: OperationRecord) -> dict[str, Any]:
    """One row for api list/search, using *effective* risk."""
    risk, reason = _effective_pair(op)
    return {
        "key": op.key,
        "method": op.http_method,
        "path": op.path,
        "risk": risk,
        "base_risk": op.risk,
        "risk_reason": reason,
        # Label the data domain so an agent searching "order"
        # cannot mistake seller sales for member purchases. Unlabeled services
        # (most of the surface) stay null rather than getting a wrong guess.
        "domain": _domain(op),
        "summary": (op.summary or "")[:120],
    }


def _effective(op: OperationRecord) -> dict[str, Any]:
    risk, reason = _effective_pair(op)
    return {"risk": risk, "reason": reason, "base_risk": op.risk}


def _effective_pair(op: OperationRecord) -> tuple[str, str | None]:
    from ..safety import effective_risk

    return effective_risk(op)


def _domain(op: OperationRecord) -> str | None:
    """The data-domain label for an operation's service, or None."""
    from ..capabilities import domain_for_service

    return domain_for_service(op.service_key)


def _is_replace_like(record: OperationRecord) -> bool:
    from ..workflows import is_replace_like

    return is_replace_like(record)


def _print_operation_table(operations: list[OperationRecord]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:  # pragma: no cover
        for op in operations:
            risk, _ = _effective_pair(op)
            click.echo(f"{op.http_method:7} {op.key:55} {op.path}  {risk}")
        return
    table = Table(title=f"{len(operations)} operation(s)", show_lines=False)
    table.add_column("METHOD", style="cyan", no_wrap=True)
    table.add_column("OPERATION")
    table.add_column("PATH")
    table.add_column("RISK", style="magenta")
    for op in operations:
        risk, _ = _effective_pair(op)
        table.add_row(op.http_method, op.key, op.path, risk)
    Console().print(table)
