"""Answering "what may this account actually call right now".

`ready: true` only means the credentials work. An account can be perfectly
configured and still be unable to call a third of the surface for want of a
scope, so both the doctor summary and the `capabilities list` filters compare
each operation's required scopes against the configured grant.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from bidkit_cli.app import build_cli

INVENTORY = "https://api.ebay.com/oauth/api_scope/sell.inventory"
BASE = "https://api.ebay.com/oauth/api_scope"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli():
    return build_cli()


def _scoped_env(monkeypatch: pytest.MonkeyPatch, scopes: str) -> None:
    """Drive the config purely from the environment, so no real config is read."""
    monkeypatch.setenv("EBAY_APP_ID", "app-PRD-1")
    monkeypatch.setenv("EBAY_CERT_ID", "cert")
    monkeypatch.setenv("EBAY_RU_NAME", "ru")
    monkeypatch.setenv("EBAY_REFRESH_TOKEN", "v^1.refresh")
    monkeypatch.setenv("EBAY_SCOPES", scopes)


def test_doctor_reports_scope_coverage(runner, cli, monkeypatch, tmp_path) -> None:
    _scoped_env(monkeypatch, f"{BASE} {INVENTORY}")
    result = runner.invoke(cli, ["--config", str(tmp_path / "none.json"),
                                 "auth", "doctor", "--format", "json"])
    assert result.exit_code == 0, result.output
    coverage = json.loads(result.output)["scope_coverage"]

    assert coverage["total"] == coverage["granted"] + coverage["blocked"]
    assert coverage["total"] > 0
    # A narrow grant must leave most of the surface unreachable; if this ever
    # reports everything granted, the comparison has stopped comparing.
    assert coverage["blocked"] > 0
    assert coverage["granted"] > 0
    # Missing scopes are named and ranked so re-consent is an informed choice.
    top = coverage["missing_scopes"][0]
    assert top["operations"] >= coverage["missing_scopes"][-1]["operations"]
    assert top["scope"].startswith("https://api.ebay.com/oauth/")


def _coverage(runner, cli, tmp_path, scopes: str) -> dict:
    result = runner.invoke(cli, ["--config", str(tmp_path / "none.json"),
                                 "auth", "doctor", "--format", "json"],
                           env={"EBAY_SCOPES": scopes})
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["scope_coverage"]


def test_coverage_tracks_the_grant(runner, cli, monkeypatch, tmp_path) -> None:
    """Coverage must follow the scopes, not report a constant.

    A config always carries at least the base ``api_scope``, and a real slice of
    the surface needs nothing more — so "no scopes" does not mean "nothing
    reachable". What must hold is that widening the grant reaches strictly more.
    """
    _scoped_env(monkeypatch, BASE)
    minimal = _coverage(runner, cli, tmp_path, BASE)
    wider = _coverage(runner, cli, tmp_path, f"{BASE} {INVENTORY}")

    assert minimal["granted"] > 0, "the base scope alone already reaches some operations"
    assert wider["granted"] > minimal["granted"], "adding a scope must unblock operations"
    assert wider["blocked"] < minimal["blocked"]
    assert minimal["total"] == wider["total"], "the surface itself does not change"


def test_scope_filters_partition_the_surface(runner, cli, monkeypatch, tmp_path) -> None:
    """--granted and --scope-blocked must be complements, not overlapping views."""
    _scoped_env(monkeypatch, f"{BASE} {INVENTORY}")
    config = ["--config", str(tmp_path / "none.json")]

    blocked = json.loads(runner.invoke(
        cli, [*config, "capabilities", "list", "--scope-blocked", "--format", "json"]
    ).output)
    granted = json.loads(runner.invoke(
        cli, [*config, "capabilities", "list", "--granted", "--format", "json"]
    ).output)

    assert blocked["operation_count"] > 0 and granted["operation_count"] > 0
    blocked_keys = {c["operation"] for c in blocked["capabilities"]}
    granted_keys = {c["operation"] for c in granted["capabilities"]}
    assert not (blocked_keys & granted_keys), "an operation cannot be both"
    assert all(c["missing_scopes"] for c in blocked["capabilities"])
    assert all(not c["missing_scopes"] for c in granted["capabilities"])


def test_scope_filters_scan_the_whole_surface_not_the_curated_view(
    runner, cli, monkeypatch, tmp_path
) -> None:
    """A missing scope is a property of the grant, not of the capability policy.

    Restricting the scan to curated entries would hide most of the answer, so
    the filters must not need --all.
    """
    _scoped_env(monkeypatch, f"{BASE} {INVENTORY}")
    config = ["--config", str(tmp_path / "none.json")]
    curated = json.loads(runner.invoke(
        cli, [*config, "capabilities", "list", "--format", "json"]
    ).output)
    blocked = json.loads(runner.invoke(
        cli, [*config, "capabilities", "list", "--scope-blocked", "--format", "json"]
    ).output)
    assert blocked["operation_count"] > curated["operation_count"]


def test_opposite_scope_filters_are_refused(runner, cli, tmp_path) -> None:
    result = runner.invoke(cli, ["--config", str(tmp_path / "none.json"), "capabilities",
                                 "list", "--scope-blocked", "--granted"])
    assert result.exit_code != 0
