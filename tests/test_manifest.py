"""Manifest loading, validation, and lookup (spec §5, §18.2)."""

from __future__ import annotations

import pytest

from bidkit_cli.manifest import AmbiguousOperation, Manifest

EXPECTED_SERVICES = 40
EXPECTED_OPERATIONS = 452


def test_manifest_counts(manifest: Manifest) -> None:
    assert manifest.data.service_count == EXPECTED_SERVICES
    assert manifest.data.operation_count == EXPECTED_OPERATIONS
    assert len(manifest.services) == EXPECTED_SERVICES
    assert len(manifest.operations) == EXPECTED_OPERATIONS
    assert manifest.data.namespace_count == 5


def test_sell_compliance_surface_is_removed(manifest: Manifest) -> None:
    """The decommissioned Sell Compliance (PBSE) REST API must stay absent.

    eBay rolled back the Product-Based Shopping Experience mandate and fully
    decommissioned the Sell Compliance REST API, so neither its service nor any
    of its operations may appear in the generated surface. This is a negative
    regression guard: a regenerated manifest must not reintroduce it.
    """
    assert "sell_compliance" not in {svc.key for svc in manifest.services}
    assert manifest.operations_for_service("sell_compliance") == []


def test_every_operation_has_unique_cli_path(manifest: Manifest) -> None:
    paths = [tuple(op.cli_path) for op in manifest.operations]
    assert len(paths) == len(set(paths))


def test_every_referenced_model_imports(manifest: Manifest) -> None:
    broken = []
    for op in manifest.operations:
        for source in (op.request, *op.responses):
            ref = getattr(source, "model_ref", None)
            if ref and ref.model:
                try:
                    ref.import_class()
                except Exception as exc:  # noqa: BLE001
                    broken.append((op.key, ref.model, str(exc)))
    assert broken == [], broken[:5]


def test_resolve_by_canonical_key(manifest: Manifest) -> None:
    op = manifest.resolve("sell_inventory.getInventoryItems")
    assert op.operation_id == "getInventoryItems"
    assert op.python_method == "get_inventory_items"
    assert op.cli_path == ["sell", "inventory", "get-inventory-items"]


def test_resolve_by_service_and_operation_id(manifest: Manifest) -> None:
    op = manifest.resolve("getInventoryItems", service="sell_inventory")
    assert op.key == "sell_inventory.getInventoryItems"
    op2 = manifest.resolve("get_inventory_items", service="sell_inventory")
    assert op2.key == "sell_inventory.getInventoryItems"


def test_post_order_namespace_exposed_as_post_order(manifest: Manifest) -> None:
    op = manifest.resolve("return.getReturn")
    assert op.namespace == "post_order"
    assert op.cli_path[0] == "post-order"
    assert op.cli_path == ["post-order", "return", "get-return"]


def test_get_by_cli_path(manifest: Manifest) -> None:
    op = manifest.get_by_cli_path(["sell", "inventory", "get-inventory-item"])
    assert op is not None
    assert op.key == "sell_inventory.getInventoryItem"


def test_ambiguous_bare_alias_raises(manifest: Manifest) -> None:
    # `search` is an operation id shared by several services (buy/marketeting/...).
    with pytest.raises(AmbiguousOperation):
        manifest.resolve("search")


def test_unknown_identifier_raises_lookuperror(manifest: Manifest) -> None:
    with pytest.raises(LookupError):
        manifest.resolve("does.notExist")
    with pytest.raises(LookupError):
        manifest.resolve("nope", service="sell_inventory")


def test_request_kind_classification(manifest: Manifest) -> None:
    cases = {
        "sell_inventory.getInventoryItems": "none",
        "sell_inventory.createOrReplaceInventoryItem": "json",
        "commerce_media.createImageFromFile": "multipart",
        "commerce_media.uploadVideo": "binary",
    }
    for key, expected in cases.items():
        op = manifest.get(key)
        assert op is not None
        assert op.request.kind == expected, key


def test_binary_response_has_stream_method(manifest: Manifest) -> None:
    op = manifest.get("sell_logistics.downloadLabelFile")
    assert op is not None
    assert op.stream_method == "stream_download_label_file"


def test_signing_required_flags(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    assert op.signing.required is True
    op = manifest.get("sell_inventory.getInventoryItems")
    assert op is not None
    assert op.signing.required is False


def test_post_order_uses_token_scheme(manifest: Manifest) -> None:
    op = manifest.get("return.getReturn")
    assert op is not None
    assert op.auth.scheme == "TOKEN"
    op = manifest.get("sell_inventory.getInventoryItems")
    assert op is not None
    assert op.auth.scheme == "Bearer"


def test_risk_classification(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItems")
    assert op is not None
    assert op.risk == "read"
    op = manifest.get("sell_inventory.createOrReplaceInventoryItem")
    assert op is not None
    assert op.risk == "write"
    op = manifest.get("sell_inventory.deleteInventoryItem")
    assert op is not None
    assert op.risk == "destructive"
    # unclassified POST fails closed by default
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    assert op.risk == "unknown"
