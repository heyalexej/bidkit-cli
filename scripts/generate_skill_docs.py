#!/usr/bin/env python3
"""Generate the progressive-disclosure skill's generated docs from the manifest.

Emits:
  skills/bidkit-cli/generated/manifest-summary.md
  skills/bidkit-cli/generated/services/<service-key>.md  (one per service)

These are generated *data* (like the manifest), not hand-edited source. Re-run after
regenerating the manifest so the docs never drift from the command surface.

    PYTHONPATH=src python scripts/generate_skill_docs.py
"""

from __future__ import annotations

from pathlib import Path

from bidkit_cli.manifest import load_manifest
from bidkit_cli.safety import effective_risk

SKILL_ROOT = Path(__file__).resolve().parent.parent / "skills" / "bidkit-cli"


def _prune_stale_service_pages(services_out: Path, expected_keys: set[str]) -> list[Path]:
    """Delete generated service pages whose service is no longer in the manifest.

    ``services_out`` holds exactly one generated page per service key, so any
    ``*.md`` whose stem is not a current service key is stale (e.g. a page left
    behind when eBay decommissions an API and it drops out of the manifest).
    Nothing outside ``services_out`` is ever touched, and current pages are kept.
    Returns the removed paths (empty when there is nothing to prune).
    """
    removed: list[Path] = []
    for page in services_out.glob("*.md"):
        if page.stem in expected_keys:
            continue
        page.unlink()
        removed.append(page)
    return removed


def main() -> None:
    manifest = load_manifest()
    services_out = SKILL_ROOT / "generated" / "services"
    services_out.mkdir(parents=True, exist_ok=True)

    # Drop stale service pages first so a removed service does not leave a
    # misleading reference behind; only *.md whose stem is no longer a current
    # service key is touched, so hand-written notes elsewhere are unaffected.
    expected_keys = {service.key for service in manifest.services}
    pruned = _prune_stale_service_pages(services_out, expected_keys)

    # Per-service reference pages.
    for service in manifest.services:
        operations = manifest.operations_for_service(service.key)
        (services_out / f"{service.key}.md").write_text(_service_page(service, operations))

    # Manifest summary (counts + namespace/service overview; never the 452-op dump).
    summary = SKILL_ROOT / "generated" / "manifest-summary.md"
    summary.write_text(_summary_page(manifest))
    print(
        f"wrote {len(manifest.services)} service pages + manifest-summary.md "
        f"-> {services_out.parent}"
        + (f" (pruned {len(pruned)} stale page(s))" if pruned else "")
    )


def _risk_cell(op) -> str:
    """Effective risk (matches the executable safety policy), with a reason for
    intentionally blocked operations (review F5).

    A progressive-disclosure skill page must not disagree with the CLI: a
    reviewed read-only POST shows ``read`` here, and a deliberately blocked
    external-side-effect POST shows ``unknown`` plus why.
    """
    risk, reason = effective_risk(op)
    cell = risk
    if reason and risk == "unknown":
        short = reason.rstrip(".").split(";")[0].strip()[:80]
        cell = f"unknown · {short}"
    return cell.replace("|", "\\|")


def _examples_section(operations) -> str:
    """One copy-pasteable safe example per operation (review 03, P1/P2).

    Rendered as a single fenced ``bash`` block with ``# <operation key>``
    comments so a reader (human or LLM) can scan a service's common calls
    without a second command. Non-safe examples are omitted here — they live in
    ``bidkit api examples <key>`` where the full safety context is visible.
    """
    lines = ["## Examples", "", "```bash"]
    for op in operations:
        safe = next((e for e in op.examples if e.safe), None)
        if safe is None:
            continue
        lines.append(f"# {op.key}")
        lines.append(safe.command)
    lines.append("```")
    lines.append("")
    lines.append(
        "More (including execute examples with the required safety flags): "
        "`bidkit api examples <service>.<operationId>`."
    )
    return "\n".join(lines)


def _service_page(service, operations) -> str:
    lines = [
        f"# {service.title}",
        "",
        f"- **Service key:** `{service.key}`",
        f"- **CLI:** `bidkit {service.cli_namespace} {service.cli_name}`",
        f"- **Version:** {service.version}",
        f"- **Base path:** `{service.base_path}`  ·  **Subdomain:** `{service.subdomain}`",
        f"- **Auth scheme:** `{service.auth_scheme}`  ·  **Requires signature:** {service.requires_signature}",
        f"- **Source spec:** `{service.source_spec}`",
        f"- **Operations:** {len(operations)}",
        "",
        "Inspect any operation's full metadata or schema without a network call:",
        "",
        "```bash",
        f"bidkit api describe {service.key}.OPERATION_ID",
        f"bidkit api schema {service.key}.OPERATION_ID request",
        "```",
        "",
        "| Operation key | Method | Path | Risk | Summary |",
        "|---|---|---|---|---|",
    ]
    for op in operations:
        summary = (op.summary or "").replace("|", "\\|").replace("\n", " ")[:90]
        risk_cell = _risk_cell(op)
        lines.append(
            f"| `{op.key}` | {op.http_method} | `{op.path}` | {risk_cell} | {summary} |"
        )
    lines.extend([
        "",
        f"Command path prefix: `bidkit {service.cli_namespace} {service.cli_name} <operation>`.",
        "",
        _examples_section(operations),
    ])
    return "\n".join(lines) + "\n"


def _summary_page(manifest) -> str:
    lines = [
        "# Generated manifest summary",
        "",
        "Machine-generated from `manifest.json`. Do not edit by hand.",
        "",
        f"- **Services:** {manifest.data.service_count}",
        f"- **Operations:** {manifest.data.operation_count}",
        f"- **Namespaces:** {manifest.data.namespace_count} ({', '.join(manifest.data.namespaces)})",
        f"- **Manifest schema version:** {manifest.data.schema_version}",
        "",
        "## Operations by namespace",
        "",
        "| Namespace | Services | Operations |",
        "|---|---|---|",
    ]
    for namespace in manifest.data.namespaces:
        cli = "post-order" if namespace == "post_order" else namespace
        svcs = [s for s in manifest.services if s.namespace == namespace]
        ops = manifest.operations_for_namespace(namespace)
        lines.append(f"| `{cli}` | {len(svcs)} | {len(ops)} |")
    lines += ["", "## Services", "", "| Service key | CLI | Title | Operations |", "|---|---|---|---|"]
    for service in sorted(manifest.services, key=lambda s: s.key):
        ops = manifest.operations_for_service(service.key)
        lines.append(
            f"| [`{service.key}`](services/{service.key}.md) "
            f"| `{service.cli_namespace} {service.cli_name}` "
            f"| {service.title} | {len(ops)} |"
        )
    lines += ["", "See `references/services/` for hand-written namespace notes."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
