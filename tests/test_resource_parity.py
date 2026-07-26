"""Manifest/resource parity.

For every manifest operation, assert the generated bidkit resource exposes the
recorded python method (and stream method when present), against the *installed*
bidkit the CLI depends on. This catches a generated surface that drifted from
the committed manifest even when the dependency range is still satisfied.
"""

from __future__ import annotations

import httpx2
import pytest
from bidkit import EbayClient, EbayConfig


@pytest.fixture(scope="module")
def client():
    return EbayClient(
        EbayConfig(access_token="t"),
        http_client=httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(200))),
    )


_NAMESPACE_ATTR = {
    "buy": "buy",
    "commerce": "commerce",
    "developer": "developer",
    "sell": "sell",
    "post_order": "post_order",
}


def test_every_manifest_method_exists_on_the_resource(client, manifest) -> None:
    missing: list[str] = []
    for op in manifest.operations:
        service = manifest.service(op.service_key)
        namespace = getattr(client, _NAMESPACE_ATTR[service.namespace])
        resource = getattr(namespace, service.python_accessor)
        if not callable(getattr(resource, op.python_method, None)):
            missing.append(op.key)
    assert missing == [], f"{len(missing)} missing methods, e.g. {missing[:5]}"


def test_every_stream_method_exists_when_declared(client, manifest) -> None:
    missing: list[str] = []
    for op in manifest.operations:
        if not op.stream_method:
            continue
        service = manifest.service(op.service_key)
        namespace = getattr(client, _NAMESPACE_ATTR[service.namespace])
        resource = getattr(namespace, service.python_accessor)
        if not callable(getattr(resource, op.stream_method, None)):
            missing.append(f"{op.key} -> {op.stream_method}")
    assert missing == [], f"{len(missing)} missing stream methods: {missing[:5]}"


def test_service_metadata_matches_manifest(client, manifest) -> None:
    mismatches: list[str] = []
    for op in manifest.operations:
        service = manifest.service(op.service_key)
        namespace = getattr(client, _NAMESPACE_ATTR[service.namespace])
        resource = getattr(namespace, service.python_accessor)
        meta = getattr(resource, "service", {})
        for field in ("key", "base_path", "subdomain"):
            if str(meta.get(field)) != str(getattr(service, field)):
                mismatches.append(
                    f"{service.key}.{field}: "
                    f"manifest={getattr(service, field)!r} sdk={meta.get(field)!r}"
                )
        # auth_scheme/requires_signature are opt-in on the Service TypedDict.
        if service.auth_scheme != "Bearer" and meta.get("auth_scheme") != service.auth_scheme:
            mismatches.append(f"{service.key}.auth_scheme mismatch")
        if service.requires_signature and not meta.get("requires_signature"):
            mismatches.append(f"{service.key}.requires_signature mismatch")
    # De-duplicate; one mismatch per (service, field) is enough signal.
    assert sorted(set(mismatches)) == [], mismatches[:5]


def test_manifest_recorded_sdk_version_matches_installed() -> None:
    import bidkit

    from bidkit_cli.manifest import load_manifest

    manifest = load_manifest()
    installed = getattr(bidkit, "__version__", None)
    if installed and manifest.data.sdk_version:
        assert installed.split(".")[:2] == manifest.data.sdk_version.split(".")[:2]
