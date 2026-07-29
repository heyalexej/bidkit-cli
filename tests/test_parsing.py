"""Input parsing (spec §9)."""

from __future__ import annotations

import pytest

from bidkit_cli.errors import UsageError, ValidationError_
from bidkit_cli.manifest import Manifest
from bidkit_cli.parsing import (
    collect_path_params,
    collect_query_params,
    parse_bool,
    parse_kv,
    read_body,
    read_multipart,
)


def test_parse_kv() -> None:
    assert parse_kv("limit=20", kind="query") == ("limit", "20")
    with pytest.raises(UsageError):
        parse_kv("noequals", kind="query")


@pytest.mark.parametrize(
    "raw,expected",
    [("true", True), ("0", False), ("yes", True), ("no", False)],
)
def test_parse_bool(raw: str, expected: bool) -> None:
    assert parse_bool(raw, name="x") is expected


def test_parse_bool_rejects_unknown() -> None:
    with pytest.raises(UsageError):
        parse_bool("maybe", name="x")


def test_path_params_positional(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None
    params = collect_path_params(op, positional=["SKU1"], universal=[])
    assert params == {"sku": "SKU1"}


def test_path_params_universal(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None
    params = collect_path_params(op, positional=[], universal=[("sku", "SKU2")])
    assert params == {"sku": "SKU2"}


def test_missing_required_path_param(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None
    with pytest.raises(UsageError):
        collect_path_params(op, positional=[], universal=[])


def test_unknown_query_rejected_unless_allowed(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItems")
    assert op is not None
    with pytest.raises(UsageError):
        collect_query_params(op, explicit={}, universal=[("bogus", "1")], allow_unknown=False)
    # allowed: no raise
    out = collect_query_params(op, explicit={}, universal=[("bogus", "1")], allow_unknown=True)
    assert out == {"bogus": "1"}


def test_repeated_value_last_wins(manifest: Manifest) -> None:
    # eBay query params are typed as strings (the transport joins lists with
    # commas); repeated non-array options keep the last value, like most CLIs.
    op = manifest.get("sell_inventory.getInventoryItems")
    assert op is not None
    out = collect_query_params(
        op, explicit={"limit": ["10", "20"]}, universal=[], allow_unknown=True,
    )
    assert out["limit"] == "20"


def test_read_body_inline_json() -> None:
    assert read_body(body_arg=None, body_json='{"a": 1}', body_file=None) == {"a": 1}


def test_read_body_rejects_both_forms() -> None:
    with pytest.raises(UsageError):
        read_body(body_arg="{}", body_json="{}", body_file=None)


def test_read_body_invalid_json(tmp_path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("{not json")
    with pytest.raises(ValidationError_):
        read_body(body_arg=f"@{f}", body_json=None, body_file=None)


def test_read_body_stdin(monkeypatch) -> None:
    import bidkit_cli.parsing as parsing

    monkeypatch.setattr(parsing.sys, "stdin", _FakeStdin('{"x": 2}'))
    assert read_body(body_arg="@-", body_json=None, body_file=None) == {"x": 2}


class _FakeStdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def test_multipart_file_field(tmp_path) -> None:
    img = tmp_path / "p.png"
    img.write_bytes(b"\x89PNG")
    files = read_multipart(file_pairs=[("image", f"@{img}")], field_pairs=[("note", "hi")])
    assert files["image"][0] == "p.png"
    assert files["image"][1] == b"\x89PNG"
    assert files["note"] == "hi"


def test_multipart_missing_file(tmp_path) -> None:
    with pytest.raises(UsageError):
        read_multipart(file_pairs=[("image", "@nope.png")], field_pairs=[])
