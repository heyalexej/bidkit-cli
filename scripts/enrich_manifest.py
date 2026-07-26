#!/usr/bin/env python3
"""Enrich the committed manifest with CLI-side metadata (review F12).

The bidkit generator emits the operation/service surface but not the SDK
version it was generated against (that field is owned by the CLI release
process, not the generator). This script stamps ``sdk_version`` onto the
committed manifest, reading it from the bidkit used to generate/regenerate.

It only rewrites ``manifest.json`` in this package — it never touches the
bidkit checkout.

    PYTHONPATH=src python scripts/enrich_manifest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import orjson

MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "bidkit_cli"
    / "generated"
    / "manifest.json"
)


def main() -> int:
    raw = orjson.loads(MANIFEST.read_bytes())
    sdk_version = _installed_bidkit_version()
    if sdk_version is None:
        print("could not import bidkit to read its version", file=sys.stderr)
        return 1
    previous = raw.get("sdk_version")
    raw["sdk_version"] = sdk_version
    # Preserve deterministic key ordering: keep the documented field order by
    # rebuilding the dict (orjson preserves insertion order).
    ordered = {
        "schema_version": raw["schema_version"],
        "sdk_package": raw.get("sdk_package", "bidkit"),
        "sdk_version": sdk_version,
        "generator_version": raw.get("generator_version", ""),
        "operation_count": raw["operation_count"],
        "service_count": raw["service_count"],
        "namespace_count": raw["namespace_count"],
        "namespaces": raw["namespaces"],
        "services": raw["services"],
        "operations": raw["operations"],
    }
    MANIFEST.write_bytes(orjson.dumps(ordered, option=orjson.OPT_INDENT_2))
    changed = previous != sdk_version
    print(
        f"manifest sdk_version = {sdk_version}"
        + (f" (was {previous})" if changed and previous else "")
        + (" [updated]" if changed else " [unchanged]")
    )
    return 0


def _installed_bidkit_version() -> str | None:
    try:
        import bidkit
    except ImportError:
        return None
    return getattr(bidkit, "__version__", None)


if __name__ == "__main__":
    raise SystemExit(main())
