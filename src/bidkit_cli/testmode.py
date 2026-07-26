"""Test-mode safety gate for destructive/scrambled test data.

A controlled test that cross-wires real inventory (a vase title, book
photographs, radio aspects, an audio category) is useful for plumbing tests but
dangerous if an agent can reproduce it without an explicit gate. This module
makes the risk legible *before* the first write and refuses publication that
does not carry an explicit test marker.

The gate applies to the inventory/offer *write* operations that carry a
description body (``createOrReplaceInventoryItem``, ``createOffer``):

* **marker requirement** — a test listing's description must contain a marker
  (default ``TEST ONLY``) so a human can recognize it on the live frontend.
  Publication is refused if the marker is absent in test mode.
* **scrambled-data gate** — when the caller declares provenance
  (``--test-provenance``) and the source SKUs differ across title/image/aspects/
  description, the CLI warns and requires ``--allow-scrambled-test-data`` together
  with the write approval, instead of silently publishing a semantically
  inconsistent combination.
* **run-id carry-through** — when a ``--test-run-id`` is given, the gate warns if
  the description/SKU do not carry it, so a test artifact is always traceable to
  its run.

The raw generated operation path stays available for expert use; this only
engages when ``--test-mode`` is set.
"""

from __future__ import annotations

from typing import Any

from .errors import ValidationError_
from .manifest import OperationRecord

# The default test marker; surfaced in inventory AND listing descriptions so
# a human can recognize a test listing on the public frontend.
DEFAULT_TEST_MARKER = "TEST ONLY"

# Operations whose request body carries a human-visible description that a test
# marker can protect. publishOffer has no body; it inherits the marker from the
# inventory item that was gated here at creation time.
_TEST_GATED_OPS = frozenset(
    {
        "sell_inventory.createOrReplaceInventoryItem",
        "sell_inventory.createOffer",
    }
)

# The provenance fields an agent is most likely to cross-wire in a test.
_PROVENANCE_FIELDS = ("title", "image", "aspects", "description", "category")


def is_test_gated(operation: OperationRecord) -> bool:
    return operation.key in _TEST_GATED_OPS


def preflight_test_mode(
    operation: OperationRecord,
    body: Any,
    *,
    test_mode: bool,
    provenance: dict[str, str] | None,
    allow_scrambled: bool,
    marker: str,
    run_id: str | None,
    allow_untracked_run: bool = False,
) -> list[str]:
    """Run the test-mode gate; raise ValidationError_ on refusal, return warnings.

    Only acts when ``test_mode`` is set and the operation is one of the
    description-carrying write ops. Returns a list of human-readable warnings
    (scrambled sources, missing run id) the caller can surface to stderr; a
    refusal is always a hard error so publication cannot proceed accidentally.
    """
    if not test_mode or not is_test_gated(operation):
        return []
    data = _as_dict(body) or {}
    warnings: list[str] = []
    # Resolve the effective marker: an explicit --test-marker wins, otherwise the
    # conventional default so the gate is meaningful even when the caller only
    # passes --test-mode.
    effective_marker = marker if marker else DEFAULT_TEST_MARKER

    # 1. Description marker must be present so the listing is recognizable.
    description = _find_description(operation, data)
    if effective_marker and (
        not isinstance(description, str) or effective_marker not in description
    ):
        raise ValidationError_(
            f"test-mode refusal: {operation.key} description must contain the "
            f"test marker {effective_marker!r} so the listing is recognizable on "
            "the live frontend; add it to the description or disable --test-mode.",
            operation=operation.key,
            details=[{"field": "description", "required_marker": effective_marker}],
        )

    # 2. Scrambled provenance must be explicitly consented to.
    if provenance:
        distinct = _distinct_sources(provenance)
        if len(distinct) > 1:
            if not allow_scrambled:
                raise ValidationError_(
                    f"test-mode refusal: {operation.key} cross-wires data from "
                    f"{len(distinct)} source SKUs ({', '.join(sorted(distinct))}); "
                    "re-run with --allow-scrambled-test-data (together with "
                    "--allow-write) to consent to a semantically inconsistent "
                    "test listing.",
                    operation=operation.key,
                    details=[{"field": k, "source_sku": v} for k, v in provenance.items()],
                )
            warnings.append(
                f"scrambled test data: {len(distinct)} source SKUs "
                f"({', '.join(sorted(distinct))}) — publication consented via "
                "--allow-scrambled-test-data."
            )

    # 3. Run id traceability: a write-heavy test workflow must not create an
    #    artifact that cannot be found from its run id. Previously a missing run
    #    id was only a warning — easy to overlook, which makes cleanup
    #    correlation optional. Now the write is refused unless the run id is
    #    present in the description/SKU OR an explicit expert override is
    #    supplied (--allow-untracked-test-run). The override still warns so an
    #    agent is informed, but the normal path can never silently lose
    #    traceability.
    if run_id:
        sku = data.get("sku")
        haystack = " ".join(
            str(v) for v in (description, sku) if isinstance(v, str)
        )
        if run_id not in haystack:
            if not allow_untracked_run:
                raise ValidationError_(
                    f"test-mode refusal: {operation.key} was started with "
                    f"--test-run-id {run_id!r} but that id is not present in the "
                    "description or SKU, so the test artifact could not be found "
                    "from its run id for cleanup. Carry the run id into the "
                    "description/SKU, or pass --allow-untracked-test-run to consent "
                    "to an untraceable test artifact.",
                    operation=operation.key,
                    details=[{"field": "run_id", "value": run_id}],
                )
            warnings.append(
                f"test run id {run_id!r} is not present in the description or SKU "
                "(consented via --allow-untracked-test-run); carry it into both so "
                "the test artifact is traceable to its run."
            )
    return warnings


def distinct_sources(provenance: dict[str, str] | None) -> list[str]:
    """Public helper for tests: the distinct non-empty source SKUs declared."""
    return _distinct_sources(provenance)


def _distinct_sources(provenance: dict[str, str] | None) -> list[str]:
    seen: list[str] = []
    for field in _PROVENANCE_FIELDS:
        value = (provenance or {}).get(field)
        if value and value not in seen:
            seen.append(str(value))
    return seen


def _find_description(operation: OperationRecord, data: dict[str, Any]) -> str | None:
    """The human-visible description for an operation, wherever it nests.

    The OAS model for ``createOffer`` uses ``listingDescription``, not
    ``description``. The previous lookup read ``data.get("description")``, so an
    OAS-correct request body (carrying only ``listingDescription``) was refused
    by the safety gate and could only pass by inventing an undocumented
    ``description`` field that then travelled on the wire. We prefer the OAS
    alias first and keep the legacy ``description`` only as a fallback.
    """
    if operation.key == "sell_inventory.createOrReplaceInventoryItem":
        product = data.get("product")
        if isinstance(product, dict):
            return product.get("description")
        return None
    if operation.key == "sell_inventory.createOffer":
        # Prefer the OAS field; accept the legacy alias only as a fallback so an
        # OAS-correct body is never forced to invent a non-OAS field.
        return data.get("listingDescription") or data.get("description")
    return data.get("description")


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    try:
        from pydantic import BaseModel
    except ImportError:  # pragma: no cover
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True)
    return None


__all__ = [
    "DEFAULT_TEST_MARKER",
    "distinct_sources",
    "is_test_gated",
    "preflight_test_mode",
]
