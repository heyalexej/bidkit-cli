"""Mutation-safety acceptance criteria: expert gates, filtered listings, help truth.

* the ``--allow-write-expert`` contract is truthful (unknown needs expert
  *and* ``--yes``; external side effects are not overridable) and the error
  payload carries the effective ``risk``.
* filtered ``api list`` counts match the active filters, generated help is
  self-contained (method/path/risk/scopes/request/response/global note), and
  every operation has manifest-backed examples reachable via ``api examples``.
* ``--include-meta`` wraps JSON as ``{meta, data}`` with a request id and no
  secrets.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import httpx2
import pytest
from bidkit import EbayClient, EbayConfig
from click.testing import CliRunner

from bidkit_cli.app import cli, main
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.errors import EXIT_SAFETY, SafetyError, report_error
from bidkit_cli.manifest import Manifest
from bidkit_cli.safety import classify_safety

# ---------------------------------------------------------------------------
# P0 — the --allow-write-expert contract is truthful
# ---------------------------------------------------------------------------

def test_p0_unknown_without_expert_gate_refused(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")  # unclassified POST
    assert op is not None
    with pytest.raises(SafetyError) as exc:
        classify_safety(op, allow_write=True, allow_write_expert=False, yes=True)
    assert exc.value.exit_code == EXIT_SAFETY
    assert exc.value.risk == "unknown"


def test_p0_unknown_with_expert_but_no_yes_refused(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    with pytest.raises(SafetyError) as exc:
        classify_safety(op, allow_write=True, allow_write_expert=True, yes=False)
    assert "--yes" in (exc.value.hint or "")


def test_p0_unknown_with_both_gates_allowed(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    risk, _ = classify_safety(op, allow_write=True, allow_write_expert=True, yes=True)
    assert risk == "unknown"


def test_p0_external_side_effect_not_overridable(manifest: Manifest) -> None:
    op = manifest.get("commerce_notification.testSubscription")
    assert op is not None
    # Even both expert gates cannot force an external side effect.
    with pytest.raises(SafetyError) as exc:
        classify_safety(op, allow_write=True, allow_write_expert=True, yes=True)
    assert "not overridable" in (exc.value.hint or "")
    assert "external side effect" in (exc.value.hint or "").lower()


def test_p0_safety_error_payload_includes_risk(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.deleteInventoryItem")
    assert op is not None
    with pytest.raises(SafetyError) as exc:
        classify_safety(op, allow_write=False, allow_write_expert=False, yes=False)
    payload = exc.value.as_dict()["error"]
    assert payload["kind"] == "safety_error"
    assert payload["risk"] == "destructive"
    assert payload["operation"] == op.key


def test_p0_report_safety_error_exits_7(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    with pytest.raises(SafetyError) as raised:
        classify_safety(op, allow_write=True, allow_write_expert=False, yes=True)
    assert report_error(raised.value, json_mode=True) == EXIT_SAFETY


def _ctx(manifest: Manifest, handler) -> CliContext:
    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    ctx.allow_write_expert = True
    ctx.yes = True
    return ctx


def test_p0_unknown_dispatches_with_both_gates(manifest: Manifest) -> None:
    """An unclassified POST really leaves the process only under both gates."""
    op = manifest.get("cancellation.checkCancellationEligibility")
    assert op is not None
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"eligible": True})

    ctx = _ctx(manifest, handler)
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(
            ctx, op, path_params={}, query_params={}, header_params={},
            body=None, files={},
        )
    assert seen, "the unknown POST was actually dispatched under both expert gates"
    assert json.loads(buf.getvalue())["eligible"] is True


def test_p0_unknown_blocked_without_expert_gate_in_execute(manifest: Manifest) -> None:
    op = manifest.get("cancellation.checkCancellationEligibility")
    assert op is not None
    ctx = _ctx(manifest, lambda r: httpx2.Response(200, json={}))
    ctx.allow_write_expert = False
    ctx.yes = True
    ctx.allow_write = True
    with pytest.raises(SafetyError):
        execute(
            ctx, op, path_params={}, query_params={}, header_params={},
            body=None, files={},
        )


def test_p0_dry_run_needs_no_gate_and_never_dispatches(manifest: Manifest) -> None:
    op = manifest.get("cancellation.checkCancellationEligibility")
    assert op is not None
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={})

    ctx = _ctx(manifest, handler)
    ctx.allow_write_expert = False
    ctx.allow_write = False
    ctx.yes = False
    ctx.dry_run = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(
            ctx, op, path_params={}, query_params={}, header_params={},
            body=None, files={},
        )
    assert not seen  # dry-run never hit the transport
    preview = json.loads(buf.getvalue())
    assert preview["dry_run"] is True
    assert preview["risk"] == "unknown"


def test_p0_cli_exit_code_7_for_unknown_without_flags(monkeypatch) -> None:
    """The real ``main()`` entry point exits 7 for a refused unknown POST.

    Uses an unclassified POST with no required body/params so input validation
    (which runs before the safety gate) does not short-circuit to exit 2/6.
    """
    monkeypatch.setattr(
        "sys.argv", ["bidkit", "api", "call", "cancellation.checkCancellationEligibility"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == EXIT_SAFETY


# ---------------------------------------------------------------------------
# P1 — filtered api list counts
# ---------------------------------------------------------------------------

def _list_json(runner: CliRunner, *extra: str) -> dict:
    result = runner.invoke(cli, ["api", "list", "--format", "json", *extra])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_p1_no_filter_counts_match_global(manifest: Manifest, runner: CliRunner) -> None:
    payload = _list_json(runner)
    assert payload["service_count"] == len(manifest.services)
    assert payload["operation_count"] == len(manifest.operations)
    assert payload["manifest"] == {
        "service_count": len(manifest.services),
        "operation_count": len(manifest.operations),
    }


def test_p1_namespace_filter_counts(manifest: Manifest, runner: CliRunner) -> None:
    payload = _list_json(runner, "--namespace", "sell")
    sell_ops = [op for op in manifest.operations if op.namespace == "sell"]
    sell_services = {op.service_key for op in sell_ops}
    assert payload["operation_count"] == len(sell_ops)
    assert payload["service_count"] == len(sell_services)
    # The manifest totals are still the global ones.
    assert payload["manifest"]["operation_count"] == len(manifest.operations)


def test_p1_service_filter_counts_one_service(runner: CliRunner, manifest: Manifest) -> None:
    payload = _list_json(runner, "--service", "sell_fulfillment")
    ops = [op for op in manifest.operations if op.service_key == "sell_fulfillment"]
    assert payload["service_count"] == 1
    assert payload["operation_count"] == len(ops)
    assert all(op["key"].startswith("sell_fulfillment.") for op in payload["operations"])


def test_p1_method_filter_counts(runner: CliRunner, manifest: Manifest) -> None:
    payload = _list_json(runner, "--method", "DELETE")
    deletes = [op for op in manifest.operations if op.http_method == "DELETE"]
    assert payload["operation_count"] == len(deletes)
    assert payload["service_count"] == len({op.service_key for op in deletes})
    assert all(op["method"] == "DELETE" for op in payload["operations"])


def test_p1_tag_filter_counts(runner: CliRunner, manifest: Manifest) -> None:
    tag = "order"
    payload = _list_json(runner, "--tag", tag)
    tagged = [op for op in manifest.operations if tag in op.tags]
    assert payload["operation_count"] == len(tagged)


def test_p1_combined_filters_count_consistently(runner: CliRunner, manifest: Manifest) -> None:
    payload = _list_json(runner, "--namespace", "sell", "--method", "GET")
    ops = [
        op for op in manifest.operations
        if op.namespace == "sell" and op.http_method == "GET"
    ]
    assert payload["operation_count"] == len(ops)
    assert payload["service_count"] == len({op.service_key for op in ops})


# ---------------------------------------------------------------------------
# P1 — generated help is self-contained
# ---------------------------------------------------------------------------

_HELP_CASES = {
    # GET with path params + scopes.
    "sell_fulfillment.getOrder": [
        "sell", "fulfillment", "get-order",
    ],
    # Read-only POST with a JSON body (effective risk read).
    "commerce_translation.translate": ["commerce", "translation", "translate"],
    # Write with a JSON body.
    "sell_inventory.createOrReplaceInventoryItem": [
        "sell", "inventory", "create-or-replace-inventory-item",
    ],
    # Multipart upload.
    "commerce_media.createImageFromFile": ["commerce", "media", "create-image-from-file"],
    # Binary download (stream).
    "sell_logistics.downloadLabelFile": [
        "sell", "logistics", "download-label-file",
    ],
}


@pytest.mark.parametrize("key,path", list(_HELP_CASES.items()))
def test_p1_help_self_contained(manifest: Manifest, runner: CliRunner, key, path) -> None:
    op = manifest.get(key)
    assert op is not None
    result = runner.invoke(cli, [*path, "--help"])
    assert result.exit_code == 0, result.output
    out = result.output
    # Canonical key + HTTP method/path.
    assert f"Operation: {op.key}" in out
    assert f"HTTP: {op.http_method} {op.path}" in out
    # Effective risk.
    from bidkit_cli.safety import effective_risk

    risk, _ = effective_risk(op)
    assert f"Risk: {risk.upper()}" in out
    # At least one scope (every eBay operation needs an OAuth scope).
    assert "Scope:" in out or "Scopes:" in out
    # Request kind.
    assert f"Request: {op.request.kind}" in out
    # Successful response media type + status.
    success = op.success_response
    assert success is not None
    assert "Success:" in out
    assert f"{success.status} " in out
    # Global-option note (informational only, no duplicate options attached).
    assert "Global options are accepted before or after the command" in out
    # At least one ready-to-run example.
    assert "Example:" in out


def test_p1_help_shows_required_inputs_before_optional(
    manifest: Manifest, runner: CliRunner
) -> None:
    result = runner.invoke(cli, ["sell", "account", "get-sales-tax", "--help"])
    assert result.exit_code == 0, result.output
    out = result.output
    # getSalesTax has required path params countryCode + jurisdictionId.
    assert "Required inputs: country-code, jurisdiction-id" in out


def test_p1_help_external_side_effect_carries_reason(manifest: Manifest, runner: CliRunner) -> None:
    result = runner.invoke(cli, ["commerce", "notification", "test-subscription", "--help"])
    assert result.exit_code == 0, result.output
    assert "Risk note:" in result.output


# ---------------------------------------------------------------------------
# P1 — manifest-backed examples and `api examples`
# ---------------------------------------------------------------------------

def test_p1_every_operation_has_at_least_one_example(manifest: Manifest) -> None:
    missing = [op.key for op in manifest.operations if not op.examples]
    assert missing == [], f"{len(missing)} operations have no examples: {missing[:5]}"


def test_p1_every_example_has_safe_flag_and_command(manifest: Manifest) -> None:
    for op in manifest.operations:
        for ex in op.examples:
            assert ex.command, op.key
            assert isinstance(ex.safe, bool)
            assert ex.kind == "command"


def test_p1_write_examples_carry_the_right_gates(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.deleteInventoryItem")
    assert op is not None
    execute_examples = [e for e in op.examples if not e.safe]
    assert execute_examples, "a destructive op should expose an execute example"
    cmd = execute_examples[0].command
    assert "--allow-write" in cmd and "--yes" in cmd


def test_p1_unknown_examples_carry_expert_and_yes(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.issueRefund")
    assert op is not None
    execute_examples = [e for e in op.examples if not e.safe]
    assert execute_examples
    cmd = execute_examples[0].command
    assert "--allow-write-expert" in cmd and "--yes" in cmd


def test_p1_external_side_effect_has_no_execute_example(manifest: Manifest) -> None:
    op = manifest.get("commerce_notification.testSubscription")
    assert op is not None
    execute_examples = [e for e in op.examples if not e.safe]
    assert execute_examples == []  # not overridable -> no execute example


def test_p1_safe_examples_never_mutate(manifest: Manifest) -> None:
    """Every safe example either is a read or carries --dry-run."""
    for op in manifest.operations:
        from bidkit_cli.safety import effective_risk

        risk, _ = effective_risk(op)
        for ex in op.examples:
            if not ex.safe:
                continue
            if risk == "read":
                continue
            assert "--dry-run" in ex.command, (op.key, ex.command)


def test_p1_api_examples_json(runner: CliRunner, manifest: Manifest) -> None:
    result = runner.invoke(
        cli, ["api", "examples", "sell_fulfillment.getOrders", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["operation"] == "sell_fulfillment.getOrders"
    assert isinstance(payload["examples"], list) and payload["examples"]
    first = payload["examples"][0]
    assert set(["command", "safe", "illustrative", "kind"]) <= set(first)


def test_p1_api_describe_includes_examples(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["api", "describe", "sell_fulfillment.getOrders"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload["examples"], list) and payload["examples"]


def test_p1_api_examples_text_mode(runner: CliRunner) -> None:
    result = runner.invoke(
        cli, ["api", "examples", "sell_fulfillment.getOrders", "--format", "text"]
    )
    assert result.exit_code == 0, result.output
    assert "# [safe]" in result.output or "# [execute]" in result.output


def test_p1_api_call_accepts_canonical_key_offline() -> None:
    """``api call`` dispatches any operation by canonical key.

    A read op under a mocked transport exercises the full dispatch path,
    including the ``dest_map`` that ``run_operation`` requires.
    """
    import httpx2
    from bidkit import EbayClient, EbayConfig

    from bidkit_cli.context import CliContext
    from bidkit_cli.manifest import load_manifest

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"orders": [], "total": 0})

    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = load_manifest()
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    op = ctx._manifest.get("sell_fulfillment.getOrders")
    assert op is not None
    buf = io.StringIO()
    with redirect_stdout(buf):
        from bidkit_cli.dispatch import execute

        execute(ctx, op, path_params={}, query_params={"limit": 5},
                header_params={}, body=None, files={})
    assert json.loads(buf.getvalue())["total"] == 0


# ---------------------------------------------------------------------------
# P2 — --include-meta
# ---------------------------------------------------------------------------

def test_p2_include_meta_wraps_payload_with_request_id(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, json={"sku": "A"},
            headers={"x-ebay-c-request-id": "REQ-123"},
        )

    ctx = _ctx(manifest, handler)
    ctx.allow_write_expert = False
    ctx.yes = False
    ctx.include_meta = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    payload = json.loads(buf.getvalue())
    assert payload["meta"] == {
        "operation": "sell_inventory.getInventoryItem",
        "http_method": "GET",
        "path": "/inventory_item/{sku}",
        "status": 200,
        "request_id": "REQ-123",
        "trace_id": None,
    }
    assert payload["data"] == {"sku": "A"}


def test_p2_include_meta_off_is_plain_payload(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sku": "A"})

    ctx = _ctx(manifest, handler)
    ctx.allow_write_expert = False
    ctx.yes = False
    ctx.include_meta = False
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    payload = json.loads(buf.getvalue())
    assert payload == {"sku": "A"}


def test_p2_include_meta_never_leaks_secrets(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, json={"sku": "A"},
            headers={"set-cookie": "SECRET", "authorization": "Bearer xyz"},
        )

    ctx = _ctx(manifest, handler)
    ctx.allow_write_expert = False
    ctx.yes = False
    ctx.include_meta = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    rendered = buf.getvalue()
    assert "Bearer xyz" not in rendered
    assert "SECRET" not in rendered


def test_p2_include_meta_with_select_applies_to_data(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")
    assert op is not None

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"sku": "A", "title": "t"})

    ctx = _ctx(manifest, handler)
    ctx.allow_write_expert = False
    ctx.yes = False
    ctx.include_meta = True
    ctx.select = "sku"
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    payload = json.loads(buf.getvalue())
    assert payload["data"] == "A"
    assert payload["meta"]["operation"] == op.key


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
