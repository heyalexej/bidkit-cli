"""Input parsing and request construction (spec §9).

Translates CLI options into the kwargs the generated SDK method expects:
path params (positional), query/header params (repeatable options or
``--query name=value``), JSON bodies (``@file`` / ``@-`` / ``--json``),
multipart (``--file`` / ``--field``), and binary (``--body-file``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import orjson

from .errors import UsageError, ValidationError_
from .manifest import OperationRecord, ParameterRecord

TRUE_LITERALS = {"true", "1", "yes"}
FALSE_LITERALS = {"false", "0", "no"}


def parse_kv(value: str, *, kind: str) -> tuple[str, str]:
    """Split ``name=value`` for --query / --header / --path / --field."""
    if "=" not in value:
        raise UsageError(f"--{kind} expects NAME=VALUE, got {value!r}")
    name, _, raw = value.partition("=")
    if not name:
        raise UsageError(f"--{kind} has an empty name in {value!r}")
    return name, raw


def parse_bool(value: str, *, name: str) -> bool:
    lowered = value.strip().lower()
    if lowered in TRUE_LITERALS:
        return True
    if lowered in FALSE_LITERALS:
        return False
    raise UsageError(
        f"--{name} expects a boolean (true/false/1/0/yes/no), got {value!r}"
    )


def coerce_scalar(raw: str, param: ParameterRecord) -> Any:
    """Best-effort type coercion using manifest metadata (spec §9.2).

    Unknown enum values are preserved (bidkit uses forward-compatible enums), and
    dates are left as ISO strings unless a model needs otherwise.
    """
    if param.type == "boolean":
        return parse_bool(raw, name=param.cli_name)
    if param.type == "integer":
        try:
            return int(raw)
        except ValueError:
            raise UsageError(
                f"--{param.cli_name} expects an integer, got {raw!r}"
            ) from None
    if param.type == "number":
        try:
            return float(raw)
        except ValueError:
            raise UsageError(
                f"--{param.cli_name} expects a number, got {raw!r}"
            ) from None
    return raw


def collect_query_params(
    operation: OperationRecord,
    *,
    explicit: dict[str, list[str]],
    universal: list[tuple[str, str]],
    allow_unknown: bool,
) -> dict[str, Any]:
    """Build the query-param mapping from named options + universal --query pairs.

    Named header options are routed elsewhere; ``explicit`` carries
    query values only. Required query parameters are enforced here, after the
    named + universal inputs are merged, so a dry-run cannot preview a request
    that eBay would reject.
    """
    by_wire = {p.wire_name: p for p in operation.query_params}
    result: dict[str, Any] = {}
    # universal --query NAME=VALUE uses wire names
    for name, raw in universal:
        param = by_wire.get(name)
        if param is None and not allow_unknown:
            raise UsageError(
                f"unknown query parameter {name!r} for {operation.key}; "
                "pass --allow-unknown-params only for experimental compatibility"
            )
        _append(result, name, raw, param)
    # named options are bucketed by the caller and keyed by wire name
    for name, values in explicit.items():
        param = by_wire.get(name)
        for raw in values:
            _append(result, name, raw, param)
    missing = [
        p.wire_name
        for p in operation.query_params
        if p.required and p.wire_name not in result
    ]
    if missing:
        raise UsageError(
            f"{operation.key} requires query parameter(s): {', '.join(missing)}"
        )
    return result


def _append(
    result: dict[str, Any], wire_name: str, raw: str, param: ParameterRecord | None
) -> None:
    value = coerce_scalar(raw, param) if param else raw
    if param and param.is_array:
        result.setdefault(wire_name, []).append(value)
    elif wire_name in result:
        # repeated non-array: last wins, mirroring usual CLI semantics
        result[wire_name] = value
    else:
        result[wire_name] = value


def collect_header_params(
    operation: OperationRecord,
    *,
    explicit: dict[str, list[str]],
    universal: list[tuple[str, str]],
    allow_unknown: bool,
) -> dict[str, str]:
    """Build the header mapping from named options + universal --header pairs.

    Named header options (``--accept``, ``--range``, ``--accept-language``) are
    routed here instead of into the query map. Headers are always
    scalar strings on the wire; required header parameters are validated later
    in dispatch, after CLI-injected defaults (e.g. ``Accept`` for binary
    downloads) are accounted for.
    """
    by_wire = {p.wire_name: p for p in operation.header_params}
    result: dict[str, str] = {}
    for name, raw in universal:
        param = by_wire.get(name)
        if param is None and not allow_unknown:
            raise UsageError(
                f"unknown header {name!r} for {operation.key}; "
                "pass --allow-unknown-params only for experimental compatibility"
            )
        result[name] = raw
    # Named options are keyed by wire name; a repeated non-array header keeps
    # the last value, mirroring usual CLI last-wins semantics.
    for name, values in explicit.items():
        result[name] = values[-1]
    return result


def collect_path_params(
    operation: OperationRecord,
    *,
    positional: list[str],
    universal: list[tuple[str, str]],
) -> dict[str, str]:
    """Bind path params positionally, with --path NAME=VALUE as the universal form."""
    path_params = operation.path_params
    result: dict[str, str] = {}
    if len(positional) > len(path_params):
        raise UsageError(
            f"{operation.key} takes {len(path_params)} path parameter(s) "
            f"but {len(positional)} were given"
        )
    for param, value in zip(path_params, positional, strict=False):
        result[param.wire_name] = value
    for name, value in universal:
        if name not in {p.wire_name for p in path_params}:
            raise UsageError(f"{name!r} is not a path parameter of {operation.key}")
        result[name] = value
    missing = [p.wire_name for p in path_params if p.wire_name not in result]
    if missing:
        raise UsageError(
            f"missing required path parameter(s) for {operation.key}: {', '.join(missing)}"
        )
    return result


def read_body(
    *,
    body_arg: str | None,
    body_json: str | None,
    body_file: str | None,
) -> Any:
    """Resolve a JSON request body from --body / --body-json / stdin (spec §9.3)."""
    if body_arg is not None and body_json is not None:
        raise UsageError("pass either --body or --body-json, not both")
    if body_file is not None and (body_arg is not None or body_json is not None):
        raise UsageError("--body-file is for binary bodies; do not combine with --body/--body-json")
    if body_json is not None:
        return _parse_json(body_json, source="--body-json")
    if body_arg is not None:
        return _read_json_source(body_arg, source="--body")
    if body_file is not None:
        return _read_bytes(body_file, source="--body-file")
    return None


def _read_json_source(spec: str, *, source: str) -> Any:
    if spec == "@-":
        data = sys.stdin.read()
        return _parse_json(data, source=f"{source} @-")
    if spec.startswith("@"):
        return _parse_json(_read_bytes(spec[1:], source=source), source=source)
    return _parse_json(spec, source=source)


def _parse_json(data: str | bytes, *, source: str) -> Any:
    try:
        return orjson.loads(data)
    except orjson.JSONDecodeError as exc:
        raise ValidationError_(
            f"invalid JSON for {source}: {exc.msg} at line {exc.lineno} col {exc.colno}"
        ) from exc


def _read_bytes(path_str: str, *, source: str) -> bytes:
    path = Path(path_str).expanduser()
    if not path.is_file():
        raise UsageError(f"{source}: file not found: {path}")
    return path.read_bytes()


def read_multipart(
    *,
    file_pairs: list[tuple[str, str]],
    field_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    """Build the ``files`` mapping the SDK multipart adapter expects.

    ``--file name=@path``  ->  {name: (filename, bytes, content_type?)}
    ``--field name=value`` ->  {name: value}   (the SDK merges files + fields)
    """
    files: dict[str, Any] = {}
    for name, spec in file_pairs:
        if not spec.startswith("@"):
            raise UsageError(f"--file {name} expects @PATH, got {spec!r}")
        path = Path(spec[1:]).expanduser()
        if not path.is_file():
            raise UsageError(f"--file {name}: file not found: {path}")
        files[name] = (path.name, path.read_bytes(), _guess_content_type(path))
    for name, value in field_pairs:
        files[name] = value
    return files


_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".avif": "image/avif",
    ".mp4": "video/mp4",
}


def _guess_content_type(path: Path) -> str | None:
    return _CONTENT_TYPES.get(path.suffix.lower())
