"""Wire fidelity: query forwarding, redaction, trace ids, example hygiene.

* allowed unknown query parameters reach the wire (no longer dropped by
  the generated fast path).
* a shared secret-redaction policy covers dry-run headers/query, raw
  response headers, and include-meta; ``Cookie``/``Set-Cookie``/signing/token
  names never print their values.
* ``--include-meta`` surfaces a trace id (``x-traffic-request-id``) and
  falls back to it for ``request_id`` when no eBay request-id header is present.
* every generated example is shell-copyable (``shlex.split``-clean, no bare
  ``<``/``>``).
* ``auth doctor`` reports ``client_credentials`` distinctly and offers
  ``--check-user-token`` to validate the configured refresh token.
"""

from __future__ import annotations

import io
import json
import shlex
from contextlib import redirect_stdout

import httpx
import pytest
from bidkit import EbayClient, EbayConfig
from click.testing import CliRunner

from bidkit_cli.app import cli
from bidkit_cli.context import CliContext
from bidkit_cli.dispatch import execute
from bidkit_cli.manifest import Manifest
from bidkit_cli.redaction import is_sensitive_name


def _ctx(manifest: Manifest, handler, *, allow_unknown_routes: bool = False) -> CliContext:
    client = EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = client
    ctx._config = client.config
    ctx.output_format = "json"
    ctx.pretty = False
    return ctx


def _dry_run(args: list[str]) -> dict:
    result = CliRunner().invoke(cli, [*args, "--dry-run", "--format", "json"])
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    if result.output.strip().startswith("{"):
        return json.loads(result.output)
    return {"_exit_code": result.exit_code, "_output": result.output}


# ---------------------------------------------------------------------------
# F1 — unknown query parameters reach the wire
# ---------------------------------------------------------------------------

def test_f1_unknown_query_reaches_the_wire(manifest: Manifest) -> None:
    """An allowed unknown query param is forwarded via the generic transport path."""
    op = manifest.get("sell_fulfillment.getOrders")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"orders": []})

    ctx = _ctx(manifest, handler)
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(
            ctx, op, path_params={}, query_params={"limit": 1, "futureParam": "VALUE"},
            header_params={}, body=None, files={},
        )
    assert seen, "the request was dispatched"
    query = seen[0].url.query.decode()
    assert "limit=1" in query
    assert "futureParam=VALUE" in query


def test_f1_unknown_query_without_flag_is_rejected(manifest: Manifest) -> None:
    """Without --allow-unknown-params an unknown query is a usage error."""
    result = CliRunner().invoke(cli, [
        "sell", "fulfillment", "get-orders",
        "--query", "futureParam=VALUE", "--dry-run", "--format", "json",
    ])
    assert result.exit_code != 0
    # The refusal happens during query collection, before dispatch.
    assert "futureParam" in (str(result.exception) + result.output)


def test_f1_unknown_query_appears_in_dry_run_preview(manifest: Manifest) -> None:
    preview = _dry_run([
        "sell", "fulfillment", "get-orders",
        "--query", "futureParam=VALUE", "--allow-unknown-params",
    ])
    assert preview["query"]["futureParam"] == "VALUE"


def test_f1_known_only_query_uses_fast_path(manifest: Manifest) -> None:
    """When no unknown params exist, dispatch still works normally."""
    op = manifest.get("sell_fulfillment.getOrders")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"orders": []})

    ctx = _ctx(manifest, handler)
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={}, query_params={"limit": 5},
                header_params={}, body=None, files={})
    assert "limit=5" in seen[0].url.query.decode()


# ---------------------------------------------------------------------------
# F2 — shared secret redaction across modes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Authorization", "authorization", "Cookie", "set-cookie",
    "X-EBAY-C-ENDUSERCTX", "x-ebay-c-enduserctx",
    "X-Ebay-Auth-Signature", "Api-Key", "X-Api-Key", "Refresh-Token",
    "Client-Secret", "User-Password",
])
def test_f2_sensitive_names_detected(name: str) -> None:
    assert is_sensitive_name(name), name


@pytest.mark.parametrize("name", [
    "Accept", "Content-Type", "Range", "Accept-Language", "X-Ebay-C-Trace-Key",
])
def test_f2_benign_names_not_flagged(name: str) -> None:
    # "key" alone must NOT be treated as sensitive (too many benign headers).
    assert not is_sensitive_name(name), name


def test_f2_dry_run_redacts_sensitive_headers(manifest: Manifest) -> None:
    preview = _dry_run([
        "sell", "fulfillment", "get-orders",
        "--header", "Cookie=SESSIONSECRET",
        "--header", "X-EBAY-C-ENDUSERCTX=affiliateId=123",
        "--allow-unknown-params",
    ])
    headers = preview["headers"]
    assert headers["Cookie"] == "<redacted>"
    assert headers["X-EBAY-C-ENDUSERCTX"] == "<redacted>"
    assert "SESSIONSECRET" not in json.dumps(preview)


def test_f2_dry_run_redacts_sensitive_query(manifest: Manifest) -> None:
    preview = _dry_run([
        "sell", "fulfillment", "get-orders",
        "--query", "access_token=T0PKEN",
        "--query", "client_secret=S3CR3T",
        "--allow-unknown-params",
    ])
    query = preview["query"]
    assert query["access_token"] == "<redacted>"
    assert query["client_secret"] == "<redacted>"
    rendered = json.dumps(preview)
    assert "T0PKEN" not in rendered
    assert "S3CR3T" not in rendered


def test_f2_raw_mode_redacts_sensitive_response_headers(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"sku": "A"},
            headers={"Authorization": "Bearer SECRET", "Set-Cookie": "session=abc"},
        )

    ctx = _ctx(manifest, handler)
    ctx.output_format = "raw"
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    payload = json.loads(buf.getvalue())
    headers = {k.lower(): v for k, v in payload["headers"].items()}
    # The keys are preserved (with a marker), but never the values.
    assert headers["authorization"] == "<redacted>"
    assert headers["set-cookie"] == "<redacted>"
    assert "SECRET" not in buf.getvalue()
    assert "session=abc" not in buf.getvalue()


def test_f2_include_meta_redacts_nothing_leaks(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"sku": "A"},
            headers={"Set-Cookie": "session=abc", "Authorization": "Bearer SECRET"},
        )

    ctx = _ctx(manifest, handler)
    ctx.include_meta = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    rendered = buf.getvalue()
    assert "SECRET" not in rendered
    assert "session=abc" not in rendered
    # meta itself only carries operation/status/ids — never headers.
    payload = json.loads(rendered)
    assert "headers" not in payload["meta"]


# ---------------------------------------------------------------------------
# F3 — trace id fallback for --include-meta
# ---------------------------------------------------------------------------

def test_f3_ebay_request_id_preferred(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"sku": "A"},
            headers={
                "x-ebay-c-request-id": "EBAY-REQ",
                "x-traffic-request-id": "TRAFFIC",
            },
        )

    ctx = _ctx(manifest, handler)
    ctx.include_meta = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    meta = json.loads(buf.getvalue())["meta"]
    assert meta["request_id"] == "EBAY-REQ"
    assert meta["trace_id"] == "TRAFFIC"


def test_f3_traffic_id_falls_back_to_request_id(manifest: Manifest) -> None:
    """When no eBay request-id header exists, request_id falls back to the trace."""
    op = manifest.get("sell_inventory.getInventoryItem")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"sku": "A"},
            headers={"x-traffic-request-id": "TRAFFIC-ONLY"},
        )

    ctx = _ctx(manifest, handler)
    ctx.include_meta = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    meta = json.loads(buf.getvalue())["meta"]
    assert meta["request_id"] == "TRAFFIC-ONLY"
    assert meta["trace_id"] == "TRAFFIC-ONLY"


def test_f3_no_trace_yields_nulls(manifest: Manifest) -> None:
    op = manifest.get("sell_inventory.getInventoryItem")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sku": "A"})

    ctx = _ctx(manifest, handler)
    ctx.include_meta = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        execute(ctx, op, path_params={"sku": "A"}, query_params={}, header_params={},
                body=None, files={})
    meta = json.loads(buf.getvalue())["meta"]
    assert meta["request_id"] is None
    assert meta["trace_id"] is None


# ---------------------------------------------------------------------------
# F4 — examples are shell-copyable
# ---------------------------------------------------------------------------

def test_f4_every_example_is_shell_safe(manifest: Manifest) -> None:
    """No example command contains a bare ``<``/``>`` or fails shlex tokenization."""
    bad: list[tuple[str, str]] = []
    for op in manifest.operations:
        for ex in op.examples:
            cmd = ex.command
            if "<" in cmd or ">" in cmd:
                bad.append((op.key, cmd))
                continue
            try:
                shlex.split(cmd)
            except ValueError as exc:
                bad.append((op.key, f"shlex error {exc}: {cmd}"))
    assert bad == [], f"{len(bad)} non-shell-safe examples, e.g. {bad[:5]}"


def test_f4_example_placeholders_are_bare_words(manifest: Manifest) -> None:
    op = manifest.get("sell_fulfillment.getOrder")  # required path param order-id
    safe = next(e for e in op.examples if e.safe)
    # The placeholder is an uppercased bare word, not ``<order-id>``.
    assert "ORDER-ID" in safe.command
    assert "<" not in safe.command


# ---------------------------------------------------------------------------
# F5 — auth doctor distinguishes client vs user token checks
# ---------------------------------------------------------------------------

@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_f5_doctor_offline_has_no_network_or_user_token(runner: CliRunner) -> None:
    """With no flags, doctor is fully offline (no token checks)."""
    result = runner.invoke(cli, ["auth", "doctor", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "network" not in payload
    assert "user_token" not in payload


def test_f5_doctor_help_documents_both_checks(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["auth", "doctor", "--help"])
    assert result.exit_code == 0, result.output
    assert "--check-network" in result.output
    assert "--check-user-token" in result.output
    # The help explains that --check-network is the client (app keyset) check.
    assert "client" in result.output.lower()


class _FakeAuth:
    def __init__(self, *, token: str | None = "TOKEN", exc: Exception | None = None) -> None:
        self._token = token
        self._exc = exc

    def access_token(self, client):  # noqa: ANN001
        if self._exc is not None:
            raise self._exc
        return self._token


class _FakeClient:
    def __init__(self, *, auth: _FakeAuth) -> None:
        self.http = None
        self.auth = auth
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeConfig:
    """Duck-typed config: supports model_copy + refresh_token attribute."""

    def __init__(self, refresh_token: str | None = "rt") -> None:
        self.refresh_token = refresh_token

    def model_copy(self, *, update: dict | None = None) -> _FakeConfig:
        refreshed = _FakeConfig(self.refresh_token)
        if update:
            for key, value in update.items():
                setattr(refreshed, key, value)
        return refreshed


def test_f5_check_network_labels_client_credentials_and_forces_client_grant(
    monkeypatch,
) -> None:
    """``--check-network`` validates the app keyset (client-credentials), even when
    a refresh token is configured, and labels it explicitly."""
    from bidkit_cli.commands import auth as auth_mod

    seen_configs: list = []

    def _fake_client(config, token_cache=None):
        seen_configs.append(config)
        return _FakeClient(auth=_FakeAuth(token="CLIENT-TOKEN"))

    monkeypatch.setattr("bidkit.EbayClient", _fake_client)
    monkeypatch.setattr("bidkit.FileTokenCache", lambda: None)

    report = auth_mod._check_network(_FakeConfig(refresh_token="rt"))
    # The client-credentials check requests the public
    # application scope only and reports which scope it validated.
    assert report["ok"] is True
    assert report["token_type"] == "client_credentials"
    assert report["scope"] == "https://api.ebay.com/oauth/api_scope"
    # The client-credentials path must clear the refresh token regardless of config.
    assert seen_configs[0].refresh_token is None
    # ... and restrict the scope to the application grant (no user-only scopes).
    assert report["scope"] in (seen_configs[0].scopes or ())


def test_f5_check_network_reports_failure(monkeypatch) -> None:
    from bidkit_cli.commands import auth as auth_mod

    def _fake_client(config, token_cache=None):
        return _FakeClient(auth=_FakeAuth(exc=RuntimeError("invalid_client")))

    monkeypatch.setattr("bidkit.EbayClient", _fake_client)
    monkeypatch.setattr("bidkit.FileTokenCache", lambda: None)
    report = auth_mod._check_network(_FakeConfig())
    assert report["ok"] is False
    assert report["token_type"] == "client_credentials"
    assert report["scope"] == "https://api.ebay.com/oauth/api_scope"
    assert "invalid_client" in report["error"]


def test_f5_check_user_token_success_never_prints_token(monkeypatch) -> None:
    from bidkit_cli.commands import auth as auth_mod

    def _fake_client(config, token_cache=None):
        return _FakeClient(auth=_FakeAuth(token="SUPERSECRET-ACCESS-TOKEN"))

    monkeypatch.setattr("bidkit.EbayClient", _fake_client)
    monkeypatch.setattr("bidkit.FileTokenCache", lambda: None)
    report = auth_mod._check_user_token(_FakeConfig(refresh_token="FAKE-REFRESH"))
    assert report == {
        "ok": True,
        "token_type": "user",
        "grant": "refresh_token",
    }
    rendered = json.dumps(report)
    assert "SUPERSECRET" not in rendered
    assert "FAKE-REFRESH" not in rendered


def test_f5_check_user_token_without_refresh_token(monkeypatch) -> None:
    from bidkit_cli.commands import auth as auth_mod

    constructed: list = []
    monkeypatch.setattr(
        "bidkit.EbayClient", lambda *a, **k: constructed.append(1) or _FakeClient(auth=_FakeAuth())
    )
    report = auth_mod._check_user_token(_FakeConfig(refresh_token=None))
    assert report["ok"] is False
    assert report["token_type"] == "user"
    assert "refresh_token" in report["error"]
    assert constructed == [], "no client should be built when there is no refresh token"


def test_f5_check_user_token_reports_refresh_failure(monkeypatch) -> None:
    from bidkit_cli.commands import auth as auth_mod

    def _fake_client(config, token_cache=None):
        return _FakeClient(auth=_FakeAuth(exc=RuntimeError("invalid_grant: expired")))

    monkeypatch.setattr("bidkit.EbayClient", _fake_client)
    monkeypatch.setattr("bidkit.FileTokenCache", lambda: None)
    report = auth_mod._check_user_token(_FakeConfig(refresh_token="rt"))
    assert report["ok"] is False
    assert "invalid_grant" in report["error"]
    assert report["token_type"] == "user"
