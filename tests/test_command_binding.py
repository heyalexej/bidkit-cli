"""Click-to-run_operation boundary: path binding, header routing, projections.

These exercise the Click-to-:func:`run_operation` dispatch boundary:

* positional path arguments bind to manifest wire names (camelCase and
  snake_case), and a universal ``--path`` can satisfy one without a positional.
* named header options (``--accept``, ``--range``, ``--accept-language``)
  reach the wire as headers, never the query string.
* required query parameters, required JSON bodies, and required
  user-provided headers are rejected locally; an auto-supplied ``Accept`` is not.
* ``--select`` array projections (``field[].child``).
* generated skill pages report effective risk, not base risk.

A manifest-driven command-adapter matrix invokes ``--help`` on every generated
operation so a param-declaration regression (e.g. the hyphenated-header crash)
cannot recur silently across the 455-op surface.
"""

from __future__ import annotations

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import httpx2
import pytest
from bidkit import EbayClient, EbayConfig
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import IoError, UsageError
from bidkit_cli.manifest import Manifest
from bidkit_cli.rendering import select_path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SKILL_GEN = Path(__file__).resolve().parent.parent / "skills" / "bidkit-cli" / "generated"


def _dry_run(args: list[str]) -> dict:
    """Invoke the CLI with --dry-run --format json and return the parsed preview."""
    result = CliRunner().invoke(cli, [*args, "--dry-run", "--format", "json"])
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    if result.output.strip().startswith("{"):
        return json.loads(result.output)
    return {"_exit_code": result.exit_code, "_output": result.output}


def _invoke(args: list[str]):
    return CliRunner().invoke(cli, args)


# ---------------------------------------------------------------------------
# F1 - positional path arguments bind to manifest wire names
# ---------------------------------------------------------------------------

def test_f1_camelcase_path_positional_binds(manifest: Manifest) -> None:
    """getOrder's path wire name is ``orderId``; the positional must reach it."""
    op = manifest.get("sell_fulfillment.getOrder")
    assert op.path_params[0].wire_name == "orderId"
    preview = _dry_run(["sell", "fulfillment", "get-order", "ORDER_ID"])
    assert preview["path_params"] == {"orderId": "ORDER_ID"}


def test_f1_snake_case_path_positional_binds(manifest: Manifest) -> None:
    op = manifest.get("buy_browse.getItem")
    assert op.path_params[0].wire_name == "item_id"
    preview = _dry_run(["buy", "browse", "get-item", "ITEM1"])
    assert preview["path_params"] == {"item_id": "ITEM1"}


def test_f1_universal_path_satisfies_without_positional(manifest: Manifest) -> None:
    """A universal --path override must not require a dummy positional value."""
    preview = _dry_run(
        ["sell", "fulfillment", "get-order", "--path", "orderId=FROM_PATH"]
    )
    assert preview["path_params"] == {"orderId": "FROM_PATH"}


def test_f1_multi_path_args_bind_in_order(manifest: Manifest) -> None:
    op = manifest.get("sell_account_v1.getSalesTax")
    assert [p.wire_name for p in op.path_params] == ["countryCode", "jurisdictionId"]
    preview = _dry_run(["sell", "account", "get-sales-tax", "US", "NY"])
    assert preview["path_params"] == {"countryCode": "US", "jurisdictionId": "NY"}


# ---------------------------------------------------------------------------
# F2 - named header options are routed to headers, not the query string
# ---------------------------------------------------------------------------

def test_f2_named_headers_routed_to_headers_not_query(manifest: Manifest) -> None:
    preview = _dry_run([
        "buy", "feed", "get-item-feed",
        "--accept", "application/json",
        "--range", "bytes=0-10",
        "--feed-scope", "ALL",
        "--category-id", "1",
    ])
    assert preview["query"] == {"feed_scope": "ALL", "category_id": "1"}
    headers = {k.lower(): v for k, v in preview["headers"].items()}
    assert headers["accept"] == "application/json"
    assert headers["range"] == "bytes=0-10"


def test_f2_hyphenated_header_option_does_not_crash(manifest: Manifest) -> None:
    """Header wire names like ``Accept-Language`` previously crashed Click."""
    preview = _dry_run(["buy", "browse", "get-item", "ITEM1", "--accept-language", "de"])
    assert preview["headers"] == {"Accept-Language": "de"}


def _recording_ctx(manifest: Manifest, handler) -> tuple[CliContext, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def _h(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(_h)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    return ctx, seen


def test_f2_named_header_reaches_the_wire(manifest: Manifest) -> None:
    """A named header option must be sent on the actual HTTP request."""
    ctx, seen = _recording_ctx(manifest, lambda req: httpx2.Response(200, json={"ok": True}))
    op = manifest.get("buy_browse.getItem")
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(
            ctx, op,
            path_params={"item_id": "X"}, query_params={},
            header_params={"Accept-Language": "de"}, body=None, files={},
        )
    assert seen[0].headers["accept-language"] == "de"


# ---------------------------------------------------------------------------
# F3 - required inputs are enforced locally (and auto-supplied headers are not)
# ---------------------------------------------------------------------------

def test_f3_missing_required_query_rejected(manifest: Manifest) -> None:
    op = manifest.get("commerce_feedback.getFeedback")
    required = {p.wire_name for p in op.query_params if p.required}
    assert {"feedback_type", "user_id"} <= required
    with pytest.raises(UsageError) as exc:
        _dry_run(["commerce", "feedback", "get-feedback"])
    assert "feedback_type" in str(exc.value)
    assert "user_id" in str(exc.value)


def test_f3_missing_required_json_body_rejected(manifest: Manifest) -> None:
    op = manifest.get("commerce_translation.translate")
    assert op.request.kind == "json" and op.request.required
    with pytest.raises(UsageError):
        _dry_run(["commerce", "translation", "translate"])


def test_f3_missing_required_header_range_rejected(manifest: Manifest) -> None:
    """Range is a required, non-auto-supplied header for getItemFeed."""
    with pytest.raises(UsageError) as exc:
        _dry_run([
            "buy", "feed", "get-item-feed",
            "--feed-scope", "ALL", "--category-id", "1",
        ])
    assert "Range" in str(exc.value)


def test_f3_required_accept_is_auto_supplied(manifest: Manifest) -> None:
    """getItemFeed requires Accept, but the CLI injects it for binary downloads."""
    preview = _dry_run([
        "buy", "feed", "get-item-feed",
        "--range", "bytes=0-10", "--feed-scope", "ALL", "--category-id", "1",
    ])
    # No --accept given, yet the required header is satisfied by injection.
    headers = {k.lower(): v for k, v in preview["headers"].items()}
    assert headers["accept"] == "text/tab-separated-values"
    assert headers["range"] == "bytes=0-10"


# ---------------------------------------------------------------------------
# F4 - --select array projections
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expression, expected", [
    ({"a": {"b": 1}}, "a.b", 1),
    ({"a": [1, 2, 3]}, "a[]", [1, 2, 3]),
    ({"item_summaries": [{"item_id": "A"}, {"item_id": "B"}]},
     "item_summaries[].item_id", ["A", "B"]),
    ({"item_summaries": []}, "item_summaries[].item_id", []),
    ({"x": [{"y": [{"z": 1}, {"z": 2}]}]}, "x[].y[].z", [[1, 2]]),
])
def test_f4_select_projections(value, expression, expected) -> None:
    assert select_path(value, expression) == expected


def test_f4_select_missing_key_error() -> None:
    with pytest.raises(IoError, match="key 'item_id' not found"):
        select_path({"item_summaries": [{"x": 1}]}, "item_summaries[].item_id")


def test_f4_select_non_list_unwrap_error() -> None:
    with pytest.raises(IoError, match="expected a list"):
        select_path({"a": 5}, "a[].b")


# ---------------------------------------------------------------------------
# F5 - generated skill pages report effective risk
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def skill_docs_module():
    spec = importlib.util.spec_from_file_location(
        "_generate_skill_docs", SCRIPTS / "generate_skill_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_f5_service_page_uses_effective_risk(manifest: Manifest, skill_docs_module) -> None:
    from bidkit_cli.safety import effective_risk

    service = manifest.service("commerce_translation")
    page = skill_docs_module._service_page(
        service, manifest.operations_for_service("commerce_translation")
    )
    op = manifest.get("commerce_translation.translate")
    risk, _ = effective_risk(op)
    assert op.risk == "unknown"          # base risk still unknown ...
    assert risk == "read"                # ... but effective risk is read
    assert "| `commerce_translation.translate` | POST |" in page
    # The risk cell in the rendered table must show the effective risk.
    row = next(line for line in page.splitlines() if "commerce_translation.translate" in line)
    assert f"| {risk} |" in row


def test_f5_blocked_operation_shows_reason(manifest: Manifest, skill_docs_module) -> None:
    service = manifest.service("commerce_notification")
    page = skill_docs_module._service_page(
        service, manifest.operations_for_service("commerce_notification")
    )
    row = next(line for line in page.splitlines() if "testSubscription" in line)
    assert "unknown · " in row          # blocked, with a human-readable reason
    assert "notification" in row.lower()


def test_f5_risk_cell_matches_cli_for_every_override(manifest: Manifest, skill_docs_module) -> None:
    """Every safety override must render the same risk the CLI enforces."""
    from bidkit_cli.safety import _OVERRIDES, effective_risk

    for override in _OVERRIDES:
        op = manifest.get(override.operation_key)
        assert op is not None
        risk, reason = effective_risk(op)
        cell = skill_docs_module._risk_cell(op)
        if risk == "unknown" and reason:
            assert cell.startswith("unknown · ")
        else:
            assert cell == risk


def test_f5_committed_pages_show_effective_risk() -> None:
    """The regenerated, committed service pages agree with the policy."""
    translate = (SKILL_GEN / "services" / "commerce_translation.md").read_text()
    row = next(line for line in translate.splitlines() if "commerce_translation.translate" in line)
    assert "| read |" in row
    blocked = (SKILL_GEN / "services" / "commerce_notification.md").read_text()
    row = next(line for line in blocked.splitlines() if "testSubscription" in line)
    assert "unknown · " in row


# ---------------------------------------------------------------------------
# Manifest-driven command-adapter matrix
# ---------------------------------------------------------------------------

def test_command_matrix_every_operation_help_is_invocable(manifest: Manifest) -> None:
    """--help must render for every generated command.

    Guards the param-declaration surface: a header wire name with a hyphen
    (``X-EBAY-C-ENDUSERCTX``) or a camelCase path dest previously crashed Click
    at invocation. Constructing the tree alone does not catch it; this does.
    """
    runner = CliRunner()
    for op in manifest.operations:
        result = runner.invoke(cli, [*op.cli_path, "--help"])
        assert result.exit_code == 0, (
            f"--help for {op.key} ({' '.join(op.cli_path)}) failed: "
            f"exit={result.exit_code} exc={result.exception!r}"
        )
