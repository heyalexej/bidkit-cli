"""CLI smoke tests via the Click test runner (spec §18.3, §18.7).

These run the actual `bidkit` executable path offline: --help at each hierarchy
level, api list/search/describe/schema, version, completion, and the global
option reordering that lets flags appear after the command.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from bidkit_cli.app import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_root_help_does_not_dump_all_operations(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    # Progressive disclosure: kebab operation names (only present in operation
    # listings) must NOT appear at the root, but the top-level groups must.
    assert "get-inventory-items" not in result.output
    assert "bulk-create-offer" not in result.output
    assert "sell" in result.output
    assert "api" in result.output


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["executable"] == "bidkit"


def test_api_list_reports_counts(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "list", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["service_count"] == 41
    assert payload["operation_count"] == 455


def test_api_list_filter_namespace(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "list", "--namespace", "sell", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert all("sell_" in op["key"] for op in payload["operations"])


def test_api_describe_works_offline(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "describe", "sell_inventory.getInventoryItems"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["key"] == "sell_inventory.getInventoryItems"
    assert payload["cli_command"] == "sell inventory get-inventory-items"
    assert payload["http_method"] == "GET"


def test_api_schema_request_works_offline(runner: CliRunner) -> None:
    result = runner.invoke(
        cli, ["api", "schema", "sell_inventory.createOrReplaceInventoryItem", "request"]
    )
    assert result.exit_code == 0
    schema = json.loads(result.output)
    assert schema["title"] == "InventoryItem"


def test_progressive_help_levels(runner: CliRunner) -> None:
    for argv in (["sell", "--help"], ["sell", "inventory", "--help"]):
        result = runner.invoke(cli, argv)
        assert result.exit_code == 0, argv
        assert "Commands:" in result.output or "Options:" in result.output


def test_operation_help(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["sell", "inventory", "get-inventory-items", "--help"])
    assert result.exit_code == 0
    assert "--limit" in result.output
    assert "Risk: READ" in result.output


def test_global_option_at_end_dry_run(runner: CliRunner) -> None:
    # --dry-run appears AFTER positional args; the reorder lets it be parsed.
    result = runner.invoke(
        cli,
        ["sell", "inventory", "create-or-replace-inventory-item", "TEST",
         "--body", '{"product":{"title":"t"}}', "--dry-run"],
    )
    # Dry-run never sends a request and does not validate the body, so a partial
    # body still yields a dry_run preview with exit 0.
    assert result.exit_code == 0, result.output + (result.stderr or "")
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["risk"] == "write"


def test_completion_no_network(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["completion", "zsh"])
    assert result.exit_code == 0
    assert "_BIDKIT_COMPLETE" in result.output


def test_post_order_namespace(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["post-order", "--help"])
    assert result.exit_code == 0


def test_unknown_operation_usage_error(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "describe", "nope.doesNotExist"])
    assert result.exit_code != 0
