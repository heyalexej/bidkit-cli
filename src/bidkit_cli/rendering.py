"""Output rendering (spec §11) and atomic file writes (spec §10.4).

JSON is the canonical automation format; tables are a conservative view that
never silently discards fields. Binary responses stream to disk atomically.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import orjson
from pydantic import BaseModel

from .context import CliContext
from .errors import IoError


def emit_json(value: Any, *, pretty: bool) -> None:
    option = orjson.OPT_INDENT_2 if pretty else 0
    sys.stdout.write(orjson.dumps(_jsonify(value), option=option).decode())
    sys.stdout.write("\n")


def _jsonify(value: Any) -> Any:
    """Normalize SDK results (Pydantic models) into JSON-serializable structures.

    Preserves eBay wire aliases (``itemId``, not ``item_id``) and keeps null
    fields (spec §11.2) so downstream automation sees the real response shape.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=False)
    if isinstance(value, list | tuple):
        return [_jsonify(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonify(val) for key, val in value.items()}
    return value


def select_path(value: Any, expression: str) -> Any:
    """Apply a tiny ``--select`` projection (spec §11.4).

    Supports a dotted path and a trailing ``[]`` to unwrap a list, e.g.
    ``item_summaries`` or ``item_summaries[].item_id`` (which maps ``item_id``
    over every element). Not a query language.
    """
    data = _jsonify(value)
    parts = expression.strip().split(".")
    for index, part in enumerate(parts):
        take_items = part.endswith("[]")
        key = part[:-2] if take_items else part
        data = _step(data, key)
        if take_items:
            if not isinstance(data, list):
                raise IoError(
                    f"--select: {part!r} expected a list, got {type(data).__name__}"
                )
            remaining = ".".join(parts[index + 1 :])
            if remaining:
                # ``field[].child`` maps ``child`` over every list element.
                return [select_path(item, remaining) for item in data]
            # ``field[]`` alone just unwraps the list.
    return data


def _step(data: Any, key: str) -> Any:
    if key == "":
        return data
    if isinstance(data, dict):
        # The documented examples (and an agent's instinct) use snake_case
        # (``item_summaries[].item_id``), but selection runs on the camelCase
        # alias dump the SDK returns (``itemSummaries[].itemId``), so the
        # snake_case form failed at runtime. Accept both: try the exact key,
        # then its snake_case/camelCase equivalents.
        if key in data:
            return data[key]
        alt = _lookup_key(data, key)
        if alt is not None:
            return data[alt]
        raise IoError(f"--select: key {key!r} not found")
    raise IoError(f"--select: cannot index {type(data).__name__} with {key!r}")


def _lookup_key(data: dict[str, Any], key: str) -> str | None:
    """Resolve a snake_case or camelCase key against a dict that may use either.

    Raises when more than one key normalizes to the same form — a payload
    carrying both ``itemId`` and ``item_id`` must not resolve silently to
    whichever iterates first.
    """
    norm = key.lower()
    matches = [c for c in data if c.lower() == norm]
    if not matches:
        # snake_case <-> camelCase: compare on the alphanumeric run only.
        compact = _compact(key)
        matches = [c for c in data if _compact(c) == compact]
    if len(matches) > 1:
        raise IoError(
            f"--select: key {key!r} is ambiguous; matches {', '.join(sorted(matches))}. "
            "Use the exact key."
        )
    return matches[0] if matches else None


def _compact(name: str) -> str:
    """Lower-case alphanumeric-only form for fuzzy key matching."""
    import re

    return re.sub(r"[^0-9A-Za-z]", "", name).lower()


def write_output_file(
    context: CliContext, data: bytes, *, destination: str
) -> Path:
    """Atomically write ``data`` to ``destination`` (spec §10.4).

    Writes a sibling temp file and renames on success; on failure the temp file
    is removed and a non-zero status surfaces. Never overwrites an existing file
    unless --force is supplied.
    """
    target = Path(destination).expanduser()
    if target.exists() and not context.force:
        raise IoError(
            f"refusing to overwrite existing file {target}; pass --force to allow"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def render_table(value: Any, *, title: str | None = None) -> str:
    """Render a conservative Rich table, falling back to JSON.

    A table is only a *view*: we identify a primary array field (items,
    inventoryItems, orders, members, ...) and project scalar fields. Anything we
    cannot sensibly tabulate is emitted as pretty JSON so no field is lost.
    """
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:  # pragma: no cover - rich is a hard dep
        return _json_fallback(value)

    data = _jsonify(value)
    rows, columns = _extract_rows(data)
    if rows is None:
        return _json_fallback(value)

    table = Table(title=title, show_lines=False, header_style="bold")
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*[_render_cell(row.get(col)) for col in columns])
    console = Console(force_terminal=_force_terminal(), highlight=False)
    with console.capture() as capture:
        console.print(table)
    return capture.get().rstrip("\n")


_PRIMARY_ARRAY_FIELDS = (
    "items",
    "inventoryItems",
    "inventoryItemResponse",
    "offers",
    "orders",
    "members",
    "item_summaries",
    "payouts",
    "transactions",
    "summaries",
    "histories",
    "errors",
)


def _extract_rows(data: Any) -> tuple[list[dict[str, Any]] | None, list[str]]:
    if isinstance(data, list):
        if not data or all(isinstance(item, dict) for item in data):
            return list(data), _columns(list(data))
        return None, []
    if isinstance(data, dict):
        for field in _PRIMARY_ARRAY_FIELDS:
            candidate = data.get(field)
            if isinstance(candidate, list) and all(
                isinstance(item, dict) for item in candidate
            ):
                return list(candidate), _columns(candidate)
    return None, []


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    # Do not silently truncate to 8 columns — the table's own docstring promises
    # "never silently discards fields", and a hidden cap is exactly that. Rich
    # folds wide tables, and the full data is one --format json away for an agent
    # who needs every field.
    return columns


def _render_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str | int | float | bool):
        return str(value)
    # nested structures: compact JSON so the column stays one line
    return orjson.dumps(value).decode()


def _json_fallback(value: Any) -> str:
    return orjson.dumps(_jsonify(value), option=orjson.OPT_INDENT_2).decode()


def _force_terminal() -> bool:
    return sys.stdout.isatty()
