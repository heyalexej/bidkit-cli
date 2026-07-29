"""Generate copy-pasteable ``bidkit`` examples for every operation.

Examples are *generated metadata*, derived deterministically from an operation's
parameters, request kind, and effective risk — never hand-written command logic.
A small :data:`CURATED_EXAMPLES` override table adds richer, reviewed examples
for the handful of operations that benefit from a real-looking body; for every
other operation the generator provides coverage.

Design goals:

* Every operation has at least one example a user (or LLM) can run.
* Safe examples (``safe=True``) never mutate state: reads, read-only POSTs, and
  ``--dry-run`` previews for writes.
* Mutating examples carry the exact safety gates they need
  (``--allow-write``, ``--yes``, ``--allow-write-expert --yes``) so a copied
  command either runs or fails closed with the right hint — never silently mutates.
* Placeholder values (``<VALUE>``, ``<order-id>``) make required inputs obvious;
  ``illustrative=True`` marks examples whose concrete values cannot be known
  without a real eBay resource id.
"""

from __future__ import annotations

from typing import Any

from .manifest import ExampleRecord, OperationRecord

# A placeholder for a required value the CLI cannot know (an id, a language, …).
# Shell-safe: a bare word, never angle brackets (``<VALUE>`` is input
# redirection in POSIX shells, so it would fail before the CLI saw it).
_VALUE = "VALUE"


def examples_for(operation: OperationRecord) -> list[ExampleRecord]:
    """Return the examples for one operation (curated override wins entirely).

    Curated overrides replace generated examples so a reviewed body is not
    duplicated or contradicted by the generator. When no override exists the
    deterministic generator below covers the operation from its metadata.
    """
    if operation.key in CURATED_EXAMPLES:
        return [ExampleRecord(**rec) for rec in CURATED_EXAMPLES[operation.key]]
    return _generate(operation)


def _generate(operation: OperationRecord) -> list[ExampleRecord]:
    from .safety import effective_risk

    risk, reason = effective_risk(operation)
    examples: list[ExampleRecord] = []

    base = f"bidkit {' '.join(operation.cli_path)}"
    positional = " ".join(_positional(p) for p in operation.path_params)
    required_query = [p for p in operation.query_params if p.required]
    required_headers = [p for p in operation.header_params if p.required]
    has_limit = any(p.wire_name == "limit" and not p.required for p in operation.query_params)

    # Always show at least one safe example. For reads that is a real call; for
    # writes/unknowns it is a --dry-run preview (which never sends).
    safe_tail: list[str] = []
    for p in required_query:
        safe_tail.append(f"--{p.cli_name} {_VALUE}")
    for p in required_headers:
        safe_tail.append(f"--{p.cli_name} {_VALUE}")
    if has_limit:
        safe_tail.append("--limit 30")
    safe_tail.append("--format json")

    if risk == "read":
        # Reads: the safe example is a real call. JSON-body read-only POSTs
        # (searchByImage, translate, findListingRecommendations) need a body.
        body_args, note = _body_args(operation)
        if body_args:
            safe_cmd = _join(base, positional, body_args, *safe_tail)
            examples.append(ExampleRecord(
                command=safe_cmd,
                safe=True,
                illustrative=True,
                note=note or "Build the request body from `bidkit api schema <key> request`.",
            ))
        else:
            examples.append(ExampleRecord(
                command=_join(base, positional, *safe_tail),
                safe=True,
                illustrative=bool(positional or required_query or required_headers),
            ))
        _extend_streaming_example(operation, base, positional, examples)
        return examples

    # Writes / unknowns: the safe example is always a --dry-run preview.
    preview_tail = list(safe_tail)
    preview_tail.append("--dry-run")
    body_args, note = _body_args(operation)
    preview_note = (
        note or "Preview the request without sending it "
        "(--dry-run never hits the network)."
    )
    # An external-side-effect override (unknown with a reason) is intentionally
    # not overridable, so only the dry-run preview is shown.
    if risk == "unknown" and reason:
        preview_note = f"Blocked from execution: {reason} (--dry-run still works)."
        examples.append(ExampleRecord(
            command=_join(base, positional, body_args, *preview_tail),
            safe=True,
            illustrative=True,
            note=preview_note,
        ))
        return examples
    examples.append(ExampleRecord(
        command=_join(base, positional, body_args, *preview_tail),
        safe=True,
        illustrative=True,
        note=preview_note,
    ))

    # The execute example carries the exact safety gates the policy requires.
    gates: list[str]
    if risk == "write":
        gates = ["--allow-write"]
    elif risk == "destructive":
        gates = ["--allow-write", "--yes"]
    elif risk == "unknown":
        # external_side_effect overrides never reach here (they are 'unknown'
        # with a reason and have no curated/generated execute path).
        gates = ["--allow-write-expert", "--yes"]
    else:  # pragma: no cover - read handled above
        gates = []

    execute_tail = [tok for tok in safe_tail if tok != "--dry-run"]
    execute_cmd = _join(base, positional, body_args, *execute_tail, *gates)
    examples.append(ExampleRecord(
        command=execute_cmd,
        safe=False,
        illustrative=True,
        note=_execute_note(risk),
    ))
    return examples


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _positional(param) -> str:
    """A shell-safe path-argument placeholder, e.g. ``ORDER-ID``.

    Uppercased cli name (no angle brackets): ``<order-id>`` would be parsed as
    input redirection in a POSIX shell, so examples stay copy-pasteable.
    """
    return param.cli_name.upper()


def _join(*tokens: Any) -> str:
    return " ".join(str(tok) for tok in tokens if tok)


def _body_args(operation: OperationRecord) -> tuple[str, str | None]:
    """Render the request-body portion of an example command.

    Returns ``(tokens, note)``. For JSON bodies we cannot synthesize a reliably
    valid object without real ids, so we point at a body file and note how to
    build it; for multipart/binary we name the required file fields.
    """
    kind = operation.request.kind
    if kind == "none":
        return "", None
    if kind == "multipart":
        file_fields = [f.name for f in operation.request.fields if f.kind == "file"]
        text_fields = [f.name for f in operation.request.fields if f.kind == "text"]
        tokens = [f"--file {name}=@./{name.replace('_', '-')}" for name in file_fields]
        # One representative text field keeps the example short.
        if text_fields:
            tokens.append(f"--field {text_fields[0]}={_VALUE}")
        return " ".join(tokens), "Replace the placeholder file paths with real files."
    if kind == "binary":
        return "--body-file ./input.bin", "Replace the placeholder with a real binary file."
    # json
    return "--body @request.json", (
        "Build request.json with `bidkit api schema <key> request`; "
        "or pass --body-json '{...}' inline."
    )


def _execute_note(risk: str) -> str:
    if risk == "destructive":
        return "Destructive: requires --allow-write --yes and deletes seller/account state."
    if risk == "unknown":
        return "Unclassified POST: forcing it is a deliberate expert action."
    return "Write: requires --allow-write and mutates account state."


def _extend_streaming_example(
    operation: OperationRecord,
    base: str,
    positional: str,
    examples: list[ExampleRecord],
) -> None:
    """Binary-download reads also benefit from an --output-file example."""
    success = operation.success_response
    if not (success and success.kind == "bytes" and operation.stream_method):
        return
    required_headers = [p for p in operation.header_params if p.required]
    tail: list[str] = []
    for p in required_headers:
        # Range/Accept placeholders for streamed downloads.
        tail.append(f"--{p.cli_name} {_VALUE}")
    tail.append("--output-file out.bin")
    tail.append("--format json")
    examples.append(ExampleRecord(
        command=_join(base, positional, *tail),
        safe=True,
        illustrative=True,
        note="Streams the binary response atomically to a file (use --force to overwrite).",
    ))


# ---------------------------------------------------------------------------
# Curated overrides
# ---------------------------------------------------------------------------

# High-value, reviewed examples keyed by canonical operation key. A curated
# entry *replaces* the generated examples for that operation, so keep it
# complete (include a dry-run/preview where the operation is not a read).
# Bodies here are illustrative shapes an agent can adapt; they are never expected
# to mutate real state without real ids.
CURATED_EXAMPLES: dict[str, list[dict[str, Any]]] = {
    # Conditionally-required search/listing operations whose
    # OAS marks the essential param optional (a useful call needs it even though
    # the schema does not require it). Without a curated override the generator
    # emits only `--limit 30`, which is not executable. These add the param an
    # agent actually needs, while staying safe (reads).
    "buy_browse.search": [
        {
            "command": "bidkit buy browse search --q VALUE --limit 30 --format json",
            "safe": True,
            "illustrative": True,
            "note": "A useful search needs --q (or --gtin/--epid/--category-ids); the "
                     "OAS marks q optional because any one of several filters suffices.",
        },
    ],
    "commerce_catalog.search": [
        {
            "command": "bidkit commerce catalog search --q VALUE --limit 30 --format json",
            "safe": True,
            "illustrative": True,
            "note": "Provide --q, --gtin, --mpn, or --category-ids; the OAS marks them "
                     "all optional but a useful call needs at least one.",
        },
    ],
    "sell_finances.getTransactionSummary": [
        {
            "command": (
                "bidkit sell finances get-transaction-summary "
                "--filter \"transactionDate:[2024-01-01T00:00:00.000Z..]\" "
                "--format json"
            ),
            "safe": True,
            "illustrative": True,
            "note": "Filter by transactionDate to scope the summary; adjust the window.",
        },
    ],
    "sell_feed.getTasks": [
        {
            "command": (
                "bidkit sell feed get-tasks --date-range \"20240101-20240131\" "
                "--format json"
            ),
            "safe": True,
            "illustrative": True,
            "note": "Scope by --date-range (and optionally --feed-type); a listing "
                     "call needs a window even though the params are optional.",
        },
    ],
    "sell_fulfillment.getOrders": [
        {
            "command": "bidkit sell fulfillment get-orders --limit 30 --format json",
            "safe": True,
            "illustrative": False,
        },
        {
            "command": (
                "bidkit sell fulfillment get-orders --filter "
                "'creationdate:[2024-01-01T00:00:00.000Z..]' --format json"
            ),
            "safe": True,
            "illustrative": True,
            "note": "Filter by creation date; adjust the window to your task.",
        },
    ],
    "sell_inventory.createOrReplaceInventoryItem": [
        {
            "command": (
                "bidkit sell inventory create-or-replace-inventory-item SKU "
                "--body @inventory-item.json --dry-run --format json"
            ),
            "safe": True,
            "illustrative": True,
            "note": (
                "Preview the PUT without sending; build the body with "
                "`bidkit api schema ... request`. For EBAY_DE add "
                "--marketplace EBAY_DE --marketplace-locale."
            ),
        },
        {
            "command": (
                "bidkit sell inventory create-or-replace-inventory-item SKU "
                "--body @inventory-item.json --allow-write --format json"
            ),
            "safe": False,
            "illustrative": True,
            "note": "Execute the upsert after reviewing the dry-run.",
        },
    ],
    "sell_inventory.updateOffer": [
        # updateOffer is a replace-like PUT — a partial body reverts omitted
        # fields to defaults. The --merge read/merge/write wrapper is the safe
        # default; the dry-run preview is the safe example, the execute examples
        # carry the gate plus the merge/verify guidance.
        {
            "command": (
                "bidkit sell inventory update-offer OFFER-ID "
                "--body @offer-patch.json --dry-run --format json"
            ),
            "safe": True,
            "illustrative": True,
            "note": (
                "Preview the PUT. updateOffer is replace-like: an omitted field "
                "reverts to the account/API default — use --merge to preserve it."
            ),
        },
        {
            "command": (
                "bidkit sell inventory update-offer OFFER-ID "
                "--body @offer-patch.json --merge --allow-write --format json"
            ),
            "safe": False,
            "illustrative": True,
            "note": (
                "--merge GETs the current offer, applies only the fields in "
                "offer-patch.json, and PUTs the merged body — omitting "
                "listingPolicies/flags no longer resets them to defaults."
            ),
        },
        {
            "command": (
                "bidkit sell inventory update-offer OFFER-ID "
                "--body @full-offer.json --allow-write --verify-live "
                "--wait-for-live 30 --format json"
            ),
            "safe": False,
            "illustrative": True,
            "note": (
                "Without --merge the body is a FULL replacement: send every "
                "field. --verify-live polls the API readback afterwards and "
                "reports 'API updated; frontend not yet confirmed'."
            ),
        },
    ],
    "commerce_media.createImageFromFile": [
        # Document the upload -> inventory composition. Upload alone does NOT
        # attach an image to a listing; the returned imageUrl must be merged into
        # an inventory item's product.imageUrls (max 24) and committed promptly,
        # because Media API URLs have expiration semantics.
        {
            "command": (
                "bidkit commerce media create-image-from-file "
                "--file image=@./photo.JPG --dry-run --format json"
            ),
            "safe": True,
            "illustrative": True,
            "note": "Preview the multipart upload without sending it.",
        },
        {
            "command": (
                "bidkit commerce media create-image-from-file "
                "--file image=@./photo.JPG --allow-write --format json"
            ),
            "safe": False,
            "illustrative": True,
            "note": (
                "Returns an eBay-hosted imageUrl (201). Then collect the URLs "
                "and put them on an inventory item's product.imageUrls "
                "(max 24, enforced by preflight) with create-or-replace-"
                "inventory-item. Commit promptly: Media API URLs expire; a stale "
                "URL will later 404 on the live listing."
            ),
        },
    ],
}
