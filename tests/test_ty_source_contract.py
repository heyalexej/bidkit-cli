"""Behavior tests for the source-contract fixes that precede ty adoption.

These assert observable behavior — not ty internals — for the spots the
type-only changes touched:

* the ``--output-file`` streaming guard raised when the path is missing,
* ``_extract_rows`` row/column extraction (all-dict / empty / mixed / nested),
* the Browse price fallback when ``price`` is missing or not a dict.

End-to-end streaming with a real ``--output-file`` is already covered by the
binary/Accept tests in ``test_header_negotiation.py``; the all-present Browse
field case is covered by ``test_testmode_and_ledger.py``.
"""

from __future__ import annotations

import pytest

from bidkit_cli.errors import UsageError
from bidkit_cli.manifest import Manifest
from bidkit_cli.rendering import _columns, _extract_rows

# --- output-file streaming guard ------------------------------------------


def test_stream_to_file_without_output_file_raises_usage_error(
    manifest: Manifest,
) -> None:
    """A missing --output-file is a structured refusal, never a bare TypeError.

    ``_stream_to_file`` is normally only reached when the streaming decision in
    ``_choose_path`` has already confirmed the path is set, so this guards the
    invariant: the failure is a clean ``UsageError`` (exit 2, structured) rather
    than a ``Path(None)`` traceback.
    """
    from bidkit_cli.context import CliContext
    from bidkit_cli.dispatch import _stream_to_file

    ctx = CliContext()
    ctx.output_file = None
    op = manifest.get("sell_inventory.getInventoryItem")
    # The guard runs before the stream context manager is entered, so a dummy
    # is safe here.
    with pytest.raises(UsageError) as exc_info:
        _stream_to_file(ctx, op, stream_context_manager=None)
    assert exc_info.value.exit_code == 2
    assert exc_info.value.kind == "usage_error"
    assert exc_info.value.operation == op.key
    assert "output-file" in exc_info.value.message


# --- rendering row/column extraction --------------------------------------


def test_extract_rows_all_dicts_keeps_order_and_unions_columns() -> None:
    rows, columns = _extract_rows([{"a": 1}, {"b": 2}, {"a": 3, "c": 4}])
    assert rows == [{"a": 1}, {"b": 2}, {"a": 3, "c": 4}]
    # Columns appear in first-seen order across rows, deduplicated.
    assert columns == ["a", "b", "c"]


def test_extract_rows_empty_list_is_valid() -> None:
    rows, columns = _extract_rows([])
    assert rows == []
    assert columns == []


def test_extract_rows_mixed_list_rejects_entirely() -> None:
    # A single non-dict element disqualifies the whole list: it is not silently
    # filtered down to its dict subset.
    rows, columns = _extract_rows([{"a": 1}, "not a dict", {"b": 2}])
    assert rows is None
    assert columns == []


def test_extract_rows_nested_primary_array_of_dicts() -> None:
    rows, columns = _extract_rows(
        {"item_summaries": [{"id": "1"}, {"id": "2", "title": "t"}]}
    )
    assert rows == [{"id": "1"}, {"id": "2", "title": "t"}]
    assert columns == ["id", "title"]


def test_extract_rows_nested_mixed_primary_array_rejects() -> None:
    # A mixed nested primary array rejects and the search does not fall through
    # to a later field just because an earlier one was present-but-mixed.
    rows, columns = _extract_rows({"item_summaries": [{"id": "1"}, "bad"]})
    assert rows is None
    assert columns == []


def test_extract_rows_scalar_returns_none() -> None:
    rows, columns = _extract_rows(42)
    assert rows is None
    assert columns == []


def test_columns_first_seen_order_no_truncation() -> None:
    # A wide row is not capped; every key is retained in first-seen order.
    row = {f"k{i}": i for i in range(12)}
    assert _columns([row]) == [f"k{i}" for i in range(12)]


# --- Browse price fallback ------------------------------------------------


def test_assert_browse_fields_missing_price_falls_back_to_none() -> None:
    from bidkit_cli.workflows import _assert_browse_fields

    results = _assert_browse_fields(
        {"itemId": "L1"},  # no "price" key at all
        expect_title=None,
        expect_description_contains=None,
        expect_image_count=None,
        expect_price="12.50",
        expect_currency="EUR",
        expect_category_id=None,
        expect_buying_option=None,
    )
    by_field = {r["field"]: r for r in results}
    assert by_field["price.value"]["observed"] is None
    assert by_field["price.value"]["match"] is False
    assert by_field["price.currency"]["observed"] is None
    assert by_field["price.currency"]["match"] is False


def test_assert_browse_fields_non_dict_price_falls_back_to_none() -> None:
    from bidkit_cli.workflows import _assert_browse_fields

    results = _assert_browse_fields(
        {"itemId": "L1", "price": "12.50"},  # price present but not a dict
        expect_title=None,
        expect_description_contains=None,
        expect_image_count=None,
        expect_price="12.50",
        expect_currency="EUR",
        expect_category_id=None,
        expect_buying_option=None,
    )
    by_field = {r["field"]: r for r in results}
    assert by_field["price.value"]["observed"] is None
    assert by_field["price.value"]["match"] is False
    assert by_field["price.currency"]["observed"] is None
    assert by_field["price.currency"]["match"] is False
