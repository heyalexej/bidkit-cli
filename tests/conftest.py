"""Shared fixtures for the bidkit-cli test suite."""

from __future__ import annotations

import httpx2
import pytest
from bidkit import EbayClient, EbayConfig

from bidkit_cli.context import CliContext
from bidkit_cli.manifest import Manifest, load_manifest


@pytest.fixture(scope="session")
def manifest() -> Manifest:
    return load_manifest()


@pytest.fixture
def mock_client():
    """An EbayClient over an httpx2.MockTransport that returns 200/{} by default."""
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"ok": True, "method": request.method,
                                        "path": request.url.path})
    return EbayClient(
        EbayConfig(access_token="token"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


@pytest.fixture
def recording_client():
    """A client that records the requests it sees and echoes them back."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"method": request.method, "url": str(request.url)})

    client = EbayClient(
        EbayConfig(access_token="token", marketplace_id="EBAY_DE"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return client, seen


@pytest.fixture
def cli_ctx(mock_client, manifest):
    """A CliContext wired to the mock-backed client (no config file needed)."""
    ctx = CliContext()
    ctx._manifest = manifest
    ctx._client = mock_client
    ctx._config = mock_client.config
    ctx.output_format = "json"
    ctx.pretty = False
    return ctx
