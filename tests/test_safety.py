"""Mutation safety model (spec §14, §18.5)."""

from __future__ import annotations

import pytest

from bidkit_cli.errors import SafetyError
from bidkit_cli.manifest import Manifest
from bidkit_cli.safety import classify_safety, effective_risk


def test_get_runs_without_flags(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItems")
    assert op is not None
    risk, _ = classify_safety(op, allow_write=False, allow_write_expert=False, yes=False)
    assert risk == "read"


def test_write_refused_without_allow_write(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    assert op is not None
    with pytest.raises(SafetyError):
        classify_safety(op, allow_write=False, allow_write_expert=False, yes=False)
    risk, _ = classify_safety(op, allow_write=True, allow_write_expert=False, yes=False)
    assert risk == "write"


def test_destructive_requires_yes(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.deleteInventoryItem")
    assert op is not None
    with pytest.raises(SafetyError):
        classify_safety(op, allow_write=True, allow_write_expert=False, yes=False)
    risk, _ = classify_safety(op, allow_write=True, allow_write_expert=False, yes=True)
    assert risk == "destructive"


def test_unknown_post_fails_closed(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    # Without the expert gate, unknown is refused even with --allow-write --yes.
    with pytest.raises(SafetyError):
        classify_safety(op, allow_write=True, allow_write_expert=False, yes=True)


def test_override_downgrades_read_post(manifest: Manifest) -> None:
    op = manifest.get("buy_browse.searchByImage")
    assert op is not None
    assert op.risk == "unknown"
    risk, reason = effective_risk(op)
    assert risk == "read"
    assert reason
