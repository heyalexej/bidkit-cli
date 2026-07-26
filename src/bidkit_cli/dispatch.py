"""Dispatch: turn a resolved operation + parsed args into an SDK call (spec §10).

Resolution uses manifest allowlists, never arbitrary ``getattr`` chains on user
input. One client per invocation; raw mode and streaming are handled here so
every command shares identical auth, retry, signing, and output behavior.

Two execution paths:

* the **fast path** calls the generated resource method (type-safe, matches the
  SDK signature exactly);
* the **generic transport path** calls ``resource._request``/``_stream`` directly
  and is used whenever a header must reach the wire that the generated method
  cannot express — CLI-injected defaults (e.g. ``Accept`` for binary responses)
  or allowed unknown ``--header`` values. Extras are never silently dropped.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import httpx2
import orjson
from bidkit.errors import (
    EbayAPIError,
    EbayAuthError,
    EbayConfigError,
    EbayTransportError,
)

from .context import CliContext
from .errors import (
    ApiError,
    ConfigError,
    IoError,
    TransportError,
    UsageError,
    ValidationError_,
)
from .manifest import OperationRecord, ParameterRecord, ServiceRecord
from .preflight import preflight
from .redaction import is_sensitive_name, redact_mapping
from .rendering import _jsonify, emit_json, select_path, write_output_file
from .safety import classify_safety, effective_risk
from .workflows import (
    enrich_publish_error,
    is_replace_like,
    merge_body,
    verify_live,
)

# namespace attr on EbayClient for each manifest namespace
_NAMESPACE_ATTR = {
    "buy": "buy",
    "commerce": "commerce",
    "developer": "developer",
    "sell": "sell",
    "post_order": "post_order",
}


# A sentinel distinguishing "the stream path already produced output" from a
# real response object (which may legitimately be None for a 204).
_STREAMED = object()


def resolve_resource(client: Any, service: ServiceRecord) -> Any:
    """client.<namespace>.<python_accessor> — via fixed allowlists only."""
    namespace_attr = _NAMESPACE_ATTR.get(service.namespace)
    if namespace_attr is None:
        raise UsageError(f"unknown namespace {service.namespace!r}")
    namespace = getattr(client, namespace_attr, None)
    if namespace is None:
        raise UsageError(f"client has no namespace {namespace_attr!r}")
    resource = getattr(namespace, service.python_accessor, None)
    if resource is None:
        raise UsageError(
            f"service {service.key!r} is not installed on the client "
            f"({namespace_attr}.{service.python_accessor})"
        )
    return resource


def build_kwargs(
    operation: OperationRecord,
    *,
    query_params: dict[str, Any],
    header_params: dict[str, str],
    body: Any,
    files: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the exact kwargs the generated method signature expects.

    Query and header params are named by their ``python_name`` (the generated
    signature uses snake_case); the resource maps them back to wire names. Only
    *known* operation headers are mapped here — extras go through the generic
    transport path (see :func:`_invoke_transport`).
    """
    kwargs: dict[str, Any] = {}
    for param in operation.parameters:
        if param.location == "query" and param.wire_name in query_params:
            kwargs[param.python_name] = query_params[param.wire_name]
        elif param.location == "header" and param.wire_name in header_params:
            kwargs[param.python_name] = header_params[param.wire_name]
    if operation.request.kind == "multipart":
        kwargs["files"] = files
    elif operation.request.kind in {"json", "binary"}:
        kwargs["body"] = body
    return kwargs


def validate_request_body(operation: OperationRecord, body: Any) -> Any:
    """Validate a JSON body against the referenced Pydantic model when one exists.

    Validation errors carry field paths (spec §9.3). On success the validated
    model is returned so the transport uses coerced/normalized values; for
    untyped bodies the parsed JSON passes through unchanged.
    """
    if operation.request.kind != "json" or body is None:
        return body
    model_cls = operation.request.model_ref.import_class()
    if model_cls is None:
        return body
    from pydantic import ValidationError

    try:
        return model_cls.model_validate(body)
    except ValidationError as exc:
        details = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        raise ValidationError_(
            f"request body for {operation.key} failed validation",
            operation=operation.key,
            details=details,
        ) from exc


def execute(
    context: CliContext,
    operation: OperationRecord,
    *,
    path_params: dict[str, str],
    query_params: dict[str, Any],
    header_params: dict[str, str],
    body: Any,
    files: dict[str, Any],
) -> None:
    """Run the validate -> (dry-run | safety -> dispatch) -> render pipeline.

    Order: inputs are validated *before* the dry-run preview, so a
    malformed body or missing required file is rejected even when previewing.
    """
    manifest = context.manifest
    service = manifest.service(operation.service_key)

    # 1. Validate inputs first. Path/query/header parsing already ran in the
    #    command layer; here we validate the request body and required
    #    binary/multipart inputs.
    validated_body = validate_request_body(operation, body)
    _enforce_required_inputs(operation, validated_body, files)

    # 1a. Local preflight: marketplace-specific limits the OpenAPI surface cannot
    #     encode (title length, image-count cap). Runs before the
    #     dry-run preview so a malformed listing is rejected even when previewing.
    preflight(
        operation, body=validated_body, marketplace_id=context.config.marketplace_id
    )

    # 1b. Test-mode safety gate: when --test-mode is set, the
    #     description-carrying write ops must carry a test marker, scrambled
    #     provenance must be explicitly consented to, and a run id is expected.
    #     Runs before dry-run so a refusal is visible even when previewing.
    from .testmode import preflight_test_mode

    test_warnings = preflight_test_mode(
        operation,
        validated_body,
        test_mode=context.test_mode,
        provenance=context.test_provenance,
        allow_scrambled=context.allow_scrambled_test_data,
        marker=context.test_marker,
        run_id=context.test_run_id,
        allow_untracked_run=context.allow_untracked_test_run,
    )
    if test_warnings:
        import sys

        for warning in test_warnings:
            sys.stderr.write(f"warning: {warning}\n")

    # 2. Split user headers into known params vs extras, then add CLI-injected
    #    defaults (Accept for binary responses). Extras only reach the wire
    #    through the generic transport path; they are never silently dropped.
    known_headers, extra_headers = _split_headers(operation, header_params)
    injected = _default_headers(operation, known_headers, extra_headers)
    extra_headers = {**injected, **extra_headers}

    # 2a. Split query params the same way: an allowed unknown
    #    query parameter must reach the wire, but the generated fast path only
    #    forwards manifest-declared params. Any unknown query forces the generic
    #    transport path so the value is not silently dropped.
    known_query, unknown_query = _split_query(operation, query_params)

    # 2b. Required header params are validated here, after injected defaults
    #    are merged, so an auto-supplied Accept (binary downloads) satisfies the
    #    manifest's required Accept while Range / Accept-Language still must be
    #    user-provided.
    _enforce_required_headers(operation, {**known_headers, **extra_headers})

    # 3. Dry-run is always allowed (no safety enforcement, no token, no network)
    #    and now runs after validation. The preview shows injected headers and is
    #    redacted by the shared secret policy. --merge is a
    #    network read, so in dry-run we cannot fetch the current state; we
    #    annotate the preview instead.
    if context.dry_run:
        _emit_dry_run(
            context, operation, service, path_params, query_params,
            {**known_headers, **extra_headers}, validated_body, files,
        )
        return

    # 4. Enforce the mutation-safety policy for real dispatch only.
    classify_safety(
        operation,
        allow_write=context.allow_write,
        allow_write_expert=context.allow_write_expert,
        yes=context.yes,
    )

    # 4a. Read/merge/write for replace-like PUTs. Must run
    #     after the safety gate (the merge is a read, but the PUT it feeds is
    #     gated) and after --dry-run (the merge needs a network read). We merge
    #     the *original* body dict, not the re-validated model, so fields the
    #     caller omitted are preserved (a model dump would stomp them with None).
    if context.merge and is_replace_like(operation):
        validated_body = merge_body(context, operation, path_params, body)
        validated_body = validate_request_body(operation, validated_body)

    # 5. Dispatch through the fast or generic path.
    client = context.client
    resource = resolve_resource(client, service)
    path_args = [path_params[p.wire_name] for p in operation.path_params]
    result = _dispatch_with_retry(
        context, resource, operation, path_args, path_params, query_params,
        known_query, unknown_query, known_headers, extra_headers,
        validated_body, files,
    )

    if result is _STREAMED:
        return  # the stream path already wrote output / emitted a summary

    # When --test-run-id is present, automatically record the
    # successful mutation to the durable ledger so a crash between publish and
    # the explicit ``record`` step can never lose the exact listing id needed for
    # cleanup. Best-effort: a recording failure must never break the real write.
    # The set of recordable operations is gated inside _record_test_event
    # (_RECORDABLE_MUTATIONS), so we only check the run id here — publishOffer is
    # unknown-risk but must still be recorded.
    if context.test_run_id:
        try:
            _record_test_event(context, operation, result, path_params, validated_body)
        except Exception:  # noqa: BLE001
            import sys

            sys.stderr.write(
                "warning: could not record test-run event to the ledger; "
                "the operation succeeded, but record it manually with "
                "`bidkit sell inventory test-run record`.\n"
            )

    _render_result(context, operation, result)

    # 6. Optional API readback verification after a successful write. The
    #    frontend listing page may lag the API, so this reports "API updated;
    #    frontend not yet confirmed" rather than implying convergence. Only
    #    meaningful for replace-like writes with a request body to compare. The
    #    report is a diagnostic on stderr so stdout stays a single JSON payload.
    if (
        context.verify_live
        and is_replace_like(operation)
        and validated_body is not None
    ):
        import sys

        wait = context.wait_for_live if context.wait_for_live > 0 else 0.0
        report = verify_live(
            context, operation, path_params, validated_body, wait_seconds=wait
        )
        sys.stderr.write(
            orjson.dumps({"verify_live": report}, option=orjson.OPT_INDENT_2).decode()
            + "\n"
        )


def _dispatch_with_retry(
    context: CliContext,
    resource: Any,
    operation: OperationRecord,
    path_args: list[str],
    path_params: dict[str, str],
    query_params: dict[str, Any],
    known_query: dict[str, Any],
    unknown_query: dict[str, Any],
    known_headers: dict[str, str],
    extra_headers: dict[str, str],
    body: Any,
    files: dict[str, Any],
) -> Any:
    """Dispatch with policy-aware retry suppression + classification (taxonomy).

    The SDK already performs bounded transport-level retry (statuses 429/500/
    502/503/504, honoring Retry-After, governed by ``--max-retries``), so this
    layer does NOT add a second retry loop — that would compound (3x3 attempts).
    Instead it does two things the SDK cannot:

    1. **Policy-aware suppression**: operations the capability policy marks
       ``retry=False`` (Leads, VeRO, eDIS, Compliance) are dispatched with the
       SDK retry budget set to zero, so a 500 on Leads is NOT retried even though
       500 is normally retriable. 403/404 are never
       retried by the SDK regardless.
    2. **Classification**: every failure is translated into a classified
       ``ApiError``/``TransportError`` carrying the stable kind, ``retryable``
       flag, Retry-After, and a bounded normalized body for HTML upstream errors,
       so an agent decides remediation deterministically.
    """
    from .capability_policy import capability_for

    policy = capability_for(operation.key)
    suppress_retry = policy is not None and not policy.retry
    saved_retry = _suppress_sdk_retry(context, suppress_retry)
    try:
        try:
            result = _dispatch(
                context, resource, operation, path_args, path_params, query_params,
                known_query, unknown_query, known_headers, extra_headers,
                body, files,
            )
        except EbayConfigError as exc:
            raise ConfigError(str(exc), operation=operation.key) from exc
        except EbayAuthError as exc:
            raise ConfigError(str(exc), operation=operation.key) from exc
        except EbayAPIError as exc:
            raise _classified_api_error(operation, exc) from exc
        except EbayTransportError as exc:
            raise _classified_transport_error(operation, exc) from exc
        if isinstance(result, httpx2.Response) and result.status_code >= 400:
            # raw_response=True suppresses the SDK's own status>=400 raise;
            # translate here to keep the exit-code / error contract uniform and
            # attach the stable classification.
            api_err = EbayAPIError.from_response(result)
            raise _classified_api_error(operation, api_err) from api_err
        return result
    finally:
        _restore_sdk_retry(context, saved_retry)


def _suppress_sdk_retry(context: CliContext, suppress: bool) -> Any:
    """Set the SDK retry budget to zero when suppressing; return saved state.

    The transport holds a reference to ``client.config`` (verified live), so
    mutating ``max_retries`` and ``retry_statuses`` here is observed by the
    transport's retry loop for this call. The original values are returned so
    :func:`_restore_sdk_retry` can put them back for any later call.
    """
    if not suppress:
        return None
    config = getattr(context.client, "config", None)
    if config is None:
        return None
    try:
        saved = (config.max_retries, getattr(config, "retry_statuses", None))
        config.max_retries = 0
        # Belt-and-suspenders: also empty the retryable-status set so a transport
        # that keys off it cannot re-enter the retry loop.
        if hasattr(config, "retry_statuses"):
            config.retry_statuses = ()
        return saved
    except Exception:  # noqa: BLE001
        return None


def _restore_sdk_retry(context: CliContext, saved: Any) -> None:
    if saved is None:
        return
    config = getattr(context.client, "config", None)
    if config is None:
        return
    max_retries, retry_statuses = saved
    try:
        config.max_retries = max_retries
        if retry_statuses is not None:
            config.retry_statuses = retry_statuses
    except Exception:  # noqa: BLE001 - restoration must never mask the real result
        pass


def _classified_api_error(
    operation: OperationRecord, exc: EbayAPIError
) -> ApiError:
    """Translate an SDK API error into a classified ApiError (error taxonomy).

    Preserves the curated publish-error hint (25002/25007/25718) and the
    non-idempotent-retry note for writes, then layers the stable classification
    on top so an agent sees both the actionable remediation and the retry
    decision. Classification is driven by the HTTP status; the body is a hint.
    """
    from .capability_policy import capability_for
    from .classification import classify_response
    from .safety import effective_risk

    response = getattr(exc, "response", None)
    content_type = response.headers.get("content-type", "") if response is not None else ""
    headers = dict(response.headers) if response is not None else None
    classification = classify_response(
        exc.status_code,
        operation=operation.key,
        body=exc.payload,
        content_type=content_type,
        request_id=exc.request_id,
        headers=headers,
    )
    # Hint precedence: the most specific remediation wins — the curated publish
    # hint (25002/25007/25718), else the classification/policy hint (which names
    # auth or entitlement remedies on any status, not just 401/403 — a Leads 500
    # on a write must name the entitlement, not only the retry mechanics). The
    # non-idempotency note for write/destructive operations is orthogonal (it is
    # about *state*, not the cause), so it is appended rather than competing.
    hint = enrich_publish_error(exc.status_code, exc.payload) or classification.hint
    eff_risk, _ = effective_risk(operation)
    if eff_risk in {"write", "destructive"}:
        note = (
            "Remote state may have changed even though this call returned an "
            "error; re-read the current state before retrying, and do not "
            "assume the mutation did not apply."
        )
        hint = f"{hint} {note}" if hint else note
    # Bound the whole error envelope, not just
    # ``normalized_body``. For a non-JSON (HTML) upstream failure the SDK puts
    # the entire page in ``payload``; echoing it verbatim into ``details`` leaks
    # the page while ``normalized_body`` carries only its 280-byte preview. We
    # drop the raw payload for non-JSON bodies and rely on the bounded
    # ``normalized_body`` preview instead.
    policy = capability_for(operation.key)
    policy_allows_retry = policy.retry if policy is not None else True
    if classification.normalized_body is not None:
        details = None
    else:
        details = [exc.payload] if exc.payload is not None else None
    return ApiError(
        str(exc),
        status=exc.status_code,
        operation=operation.key,
        request_id=exc.request_id,
        details=details,
        hint=hint,
        classification=classification.kind,
        retryable=classification.retry and policy_allows_retry,
        retry_after=classification.retry_after,
        normalized_body=classification.normalized_body,
    )


def _classified_transport_error(
    operation: OperationRecord, exc: EbayTransportError
) -> TransportError:
    """A transport failure is always classified transport_error (bounded retry).

    The retry decision honors the capability policy — a Leads
    timeout is NOT retried even though timeouts are normally retriable, because
    Leads is policy-suppressed (retry=False) just as a Leads 500 is.
    """
    from .capability_policy import capability_for

    policy = capability_for(operation.key)
    policy_allows_retry = policy.retry if policy is not None else True
    return TransportError(
        str(exc),
        operation=operation.key,
        classification="transport_error",
        retryable=policy_allows_retry,
        hint=(
            "The request did not complete reliably (timeout/network); "
            "retry with bounded backoff and re-read state before retrying a write."
        ),
    )


def _dispatch(
    context: CliContext,
    resource: Any,
    operation: OperationRecord,
    path_args: list[str],
    path_params: dict[str, str],
    query_params: dict[str, Any],
    known_query: dict[str, Any],
    unknown_query: dict[str, Any],
    known_headers: dict[str, str],
    extra_headers: dict[str, str],
    body: Any,
    files: dict[str, Any],
) -> Any:
    """Pick the fast (generated method) or generic (transport) path.

    The generic path is used whenever a value must reach the wire that the
    generated method signature cannot express: injected/extra *headers*
    **or** allowed unknown *query* parameters. The fast
    path's ``build_kwargs`` only forwards manifest-declared query params, so an
    unknown query would otherwise be silently dropped despite the preview.
    """
    streaming = bool(operation.stream_method and context.output_file)
    if extra_headers or unknown_query:
        return _invoke_transport(
            context, resource, operation, path_params, query_params,
            known_headers, extra_headers, body, files, streaming,
        )
    method = _get_method(resource, operation)
    kwargs = build_kwargs(
        operation,
        query_params=known_query,
        header_params=known_headers,
        body=body,
        files=files,
    )
    if streaming:
        _stream_to_file(context, operation, method(*path_args, **kwargs))
        return _STREAMED
    return method(*path_args, raw_response=True, **kwargs)


def _invoke_transport(
    context: CliContext,
    resource: Any,
    operation: OperationRecord,
    path_params: dict[str, str],
    query_params: dict[str, Any],
    known_headers: dict[str, str],
    extra_headers: dict[str, str],
    body: Any,
    files: dict[str, Any],
    streaming: bool,
) -> Any:
    """Generic transport call used when extra/injected headers must reach the wire.

    Mirrors what the generated method does (``resource._request`` / ``_stream``)
    but with a fully-controlled wire-name header dict, so injected defaults
    (Accept for binary responses) and allowed unknown ``--header`` values are
    actually sent instead of being dropped by the fixed generated signature.
    """
    headers = _build_transport_headers(operation, known_headers, extra_headers)
    common: dict[str, Any] = {
        "operation_id": operation.operation_id,
        "method": operation.http_method,
        "path": operation.path,
        "path_params": path_params,
        "params": query_params,
        "headers": headers,
    }
    if operation.request.kind == "multipart":
        common["files"] = files
    elif operation.request.kind in {"json", "binary"}:
        common["body"] = body
    sign = True if operation.signing.required else None
    if streaming:
        # The stream path does not sign (no signed operation is a binary stream).
        _stream_to_file(context, operation, resource._stream(**common))
        return _STREAMED
    return resource._request(
        **common,
        response_model=_response_model_value(operation),
        raw_response=True,
        sign=sign,
    )


def _split_headers(
    operation: OperationRecord, header_params: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    """Separate headers that match a manifest param from unknown extras.

    Matching is case-insensitive (the manifest stores the
    canonical ``Accept`` / ``Accept-Language``; a caller may pass
    ``--header accept=...``), so a lower-cased ``--header`` value binds to the
    known param instead of falling through to extras and double-reaching the wire.
    """
    return _split_known(operation.header_params, header_params, case_insensitive=True)


def _split_query(
    operation: OperationRecord, query_params: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separate manifest query params from allowed unknown ones.

    Mirrors :func:`_split_headers`: unknown query keys must travel through the
    generic transport path, because the generated fast path only forwards
    manifest-declared query parameters. Query matching stays case-sensitive
    (eBay query params are case-significant camelCase).
    """
    return _split_known(operation.query_params, query_params, case_insensitive=False)


def _split_known(
    params: list[ParameterRecord],
    provided: dict[str, Any],
    *,
    case_insensitive: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shared split for headers/query: one implementation, not two."""
    known_wire = {p.wire_name for p in params}
    if case_insensitive:
        known_lower = {w.lower() for w in known_wire}
        # Map the provided key back to the canonical wire name when it matches.
        canonical = {w.lower(): w for w in known_wire}
    known: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in provided.items():
        if case_insensitive and key.lower() in known_lower:
            known[canonical[key.lower()]] = value
        elif not case_insensitive and key in known_wire:
            known[key] = value
        else:
            extra[key] = value
    return known, extra


def _default_headers(
    operation: OperationRecord,
    known_headers: dict[str, str],
    extra_headers: dict[str, str],
) -> dict[str, str]:
    """CLI-injected header defaults.

    Binary-response operations (Feed/logistics file downloads) must negotiate
    their real media type; the SDK transport otherwise defaults ``Accept`` to
    ``application/json`` and eBay returns 406. We inject the success response's
    content type unless the caller already supplied ``Accept`` anywhere. An
    operation may declare a 204 *before* its 200 bytes body, so scan every
    success response for a bytes one rather than trusting the first.
    """
    bytes_success = next(
        (r for r in operation.success_responses if r.kind == "bytes"), None
    )
    if not (bytes_success and bytes_success.content_type):
        return {}
    accept = bytes_success.content_type.split(";", 1)[0].strip()
    supplied = any(key.lower() == "accept" for key in (*known_headers, *extra_headers))
    if supplied:
        return {}
    return {"Accept": accept}


def _sdk_default_headers(context: CliContext) -> dict[str, str]:
    """The SDK transport's config-derived default headers.

    Mirrors ``bidkit.transport._headers`` so the dry-run preview reports exactly
    the headers the wire request will carry in addition to the explicit
    user/param headers: a default ``Accept``, the marketplace id, and the
    resolved Content/Accept-Language. Sensitive names go through the shared
    redaction policy (none of these are sensitive today, but the policy keeps
    the preview honest if a credential ever lands here).
    """
    config = context.config
    headers: dict[str, str] = {
        "Accept": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": config.marketplace_id,
    }
    if config.accept_language:
        headers["Accept-Language"] = config.accept_language
    if config.content_language:
        headers["Content-Language"] = config.content_language
    return headers


def _build_transport_headers(
    operation: OperationRecord,
    known_headers: dict[str, str],
    extra_headers: dict[str, str],
) -> dict[str, str]:
    """Wire-name header dict for the generic transport path.

    Mirrors the generated method: known params + extras + a Content-Type for
    json/binary request bodies (the resource derives Content-Type from the body
    otherwise).
    """
    headers = {**known_headers, **extra_headers}
    if operation.request.kind in {"json", "binary"} and operation.request.content_type:
        headers.setdefault("Content-Type", operation.request.content_type)
    return headers


def _response_model_value(operation: OperationRecord) -> Any:
    """Resolve the response_model argument the generated method would pass."""
    success = operation.success_response
    if success is None:
        return None
    if success.kind == "bytes":
        return bytes
    if success.kind == "text":
        return str
    if success.kind == "json":
        return success.model_ref.import_class()  # None for untyped JSON
    return None


def _enforce_required_inputs(
    operation: OperationRecord, body: Any, files: dict[str, Any]
) -> None:
    """Reject missing required inputs before preview/dispatch."""
    if operation.request.kind == "json" and operation.request.required and body is None:
        raise UsageError(
            f"{operation.key} requires a JSON request body; pass --body @file.json "
            "or --body-json '{...}'"
        )
    if operation.request.kind == "binary" and operation.request.required and body is None:
        raise UsageError(f"{operation.key} requires a binary body; pass --body-file PATH")
    if operation.request.kind == "multipart":
        missing = [
            field.name
            for field in operation.request.fields
            if field.required and field.kind == "file" and field.name not in files
        ]
        if missing:
            raise UsageError(
                f"{operation.key} requires multipart file field(s): {', '.join(missing)}"
            )


def _enforce_required_headers(
    operation: OperationRecord, headers: dict[str, str]
) -> None:
    """Reject missing required header params after merging injected defaults.

    Comparison is case-insensitive because callers may pass ``--header
    accept=...`` or the named ``--accept`` while the manifest stores the
    canonical ``Accept``.
    """
    present = {key.lower() for key in headers}
    missing = [
        param.wire_name
        for param in operation.header_params
        if param.required and param.wire_name.lower() not in present
    ]
    if missing:
        raise UsageError(
            f"{operation.key} requires header parameter(s): {', '.join(missing)}"
        )


def _get_method(resource: Any, operation: OperationRecord) -> Any:
    method = getattr(resource, operation.python_method, None)
    if method is None or not callable(method):
        raise UsageError(
            f"generated resource has no method {operation.python_method!r} for {operation.key}"
        )
    return method


def _stream_to_file(
    context: CliContext,
    operation: OperationRecord,
    stream_context_manager: Any,
) -> None:
    """Stream a binary response to ``--output-file`` atomically.

    Takes the already-built stream context manager (from either the generated
    ``stream_<method>`` or ``resource._stream``) so the generic and fast paths
    share identical output behavior.
    """
    target = Path(context.output_file).expanduser()
    if target.exists() and not context.force:
        raise IoError(f"refusing to overwrite {target}; pass --force to allow")
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    status: int | None = None
    request_id: str | None = None
    trace_id: str | None = None
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with stream_context_manager as response:
            if response.status_code >= 400:
                raise ApiError(
                    f"{operation.key} failed",
                    status=response.status_code,
                    operation=operation.key,
                    request_id=response.headers.get("x-ebay-c-request-id"),
                )
            status = response.status_code
            request_id = _request_id(response)
            trace_id = _trace_id(response)
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    written += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    if not context.json_mode:
        import sys

        sys.stderr.write(f"wrote {written} bytes to {target}\n")
    else:
        summary: dict[str, Any] = {
            "operation": operation.key,
            "bytes": written,
            "file": str(target),
        }
        # --include-meta adds status + traceability ids to the stream summary
        # too, including the traffic-trace id as a fallback.
        if context.include_meta:
            summary["status"] = status
            summary["request_id"] = request_id or trace_id
            summary["trace_id"] = trace_id
        emit_json(summary, pretty=context.pretty)


def _render_result(context: CliContext, operation: OperationRecord, result: Any) -> None:
    if not isinstance(result, httpx2.Response):
        emit_json(result, pretty=context.pretty)
        return

    content_type = result.headers.get("content-type", "")
    if "json" in content_type:
        body: Any = orjson.loads(result.content) if result.content else None
    elif result.content and any(r.kind == "text" for r in operation.success_responses):
        body = result.text
    elif result.content:
        body = result.content
    else:
        body = None

    if isinstance(body, bytes | bytearray):
        if context.output_file:
            write_output_file(context, bytes(body), destination=context.output_file)
            return
        if not context.json_mode:
            import sys

            sys.stderr.write(
                f"received {len(body)} bytes (binary); use --output-file to save\n"
            )
            return
        raise IoError(
            f"{operation.key} returned a binary response; "
            "use --output-file PATH (raw mode embeds no bytes in JSON)"
        )

    raw_response = context.effective_format == "raw"
    payload: Any = body
    if raw_response:
        payload = {
            "status": result.status_code,
            "headers": _filter_headers(result.headers),
            "body": body,
        }
    if context.select:
        payload = select_path(payload, context.select)

    fmt = context.effective_format
    # --include-meta wraps the JSON payload in {meta, data}. It
    # only applies to JSON-shaped output; --format raw keeps its own envelope and
    # table/text are for humans. Meta never carries auth/cookie/signing headers.
    wrap_meta = (
        context.include_meta
        and not raw_response
        and (fmt == "json" or context.json_mode)
    )
    if wrap_meta:
        payload = {"meta": _response_meta(operation, result), "data": payload}

    if fmt == "json" or context.json_mode or raw_response or context.select:
        emit_json(payload, pretty=context.pretty)
    elif fmt == "table" and isinstance(payload, dict | list):
        import sys

        from .rendering import render_table

        sys.stdout.write(render_table(payload, title=operation.key) + "\n")
    elif fmt == "text" and isinstance(payload, str):
        import sys

        sys.stdout.write(payload + "\n")
    else:
        emit_json(payload, pretty=context.pretty)


# Operations whose successful response carries an id worth recording.
# For these we extract the id from the response body or path params and append a
# durable event to the run ledger when --test-run-id is present.
_RECORDABLE_MUTATIONS = {
    "sell_inventory.createOrReplaceInventoryItem",
    "sell_inventory.createOffer",
    "sell_inventory.publishOffer",
    "sell_inventory.withdrawOffer",
    "sell_inventory.deleteInventoryItem",
    "sell_inventory.deleteOffer",
}


def _record_test_event(
    context: CliContext,
    operation: OperationRecord,
    result: Any,
    path_params: dict[str, str],
    request_body: Any = None,
) -> None:
    """Append a durable event to the run ledger.

    Records sku/offer_id/listing_id, the operation, HTTP status, and eBay's
    request/trace ids for every successful mutation on a recordable operation
    when ``--test-run-id`` is set. Idempotent: re-recording the same id is a
    no-op at the ledger level (add_test_sku/add_offer/add_listing dedupe). The
    event stream itself is append-only and never deduped, so a retried write is
    visible as two events.

    Implementation notes:
    * path params are keyed by **wire name** (``offerId``), not the python name
      (``offer_id``); the previous lookup always returned None for offer ops.
    * the SKU for ``createOffer`` is taken from the request body, which the
      recorder now receives (``request_body``); createOffer has no path params.
    * the ledger is auto-created on the first recorded event so auto-recording
      no longer degrades to a stderr warning when ``test-run init`` was skipped.
    """
    if operation.key not in _RECORDABLE_MUTATIONS:
        return
    from .ledger import RunEvent, save_ledger

    status: int | None = None
    body: Any = None
    request_id = trace_id = None
    if isinstance(result, httpx2.Response):
        status = result.status_code
        request_id = _request_id(result)
        trace_id = _trace_id(result)
        content_type = result.headers.get("content-type", "")
        if "json" in content_type and result.content:
            try:
                body = orjson.loads(result.content)
            except orjson.JSONDecodeError:
                body = None
    response_body = body if isinstance(body, dict) else {}
    req_body = _body_as_dict(request_body)

    # Path params are keyed by wire name. publishOffer/withdrawOffer/
    # deleteOffer carry ``offerId``; createOrReplaceInventoryItem/deleteInventoryItem
    # carry ``sku``. The python names (offer_id/sku) are NOT the keys.
    sku = (
        path_params.get("sku")
        or req_body.get("sku")
        or response_body.get("sku")
    )
    offer_id = (
        path_params.get("offerId")
        or req_body.get("offerId")
        or response_body.get("offerId")
    )
    listing_id = response_body.get("listingId")
    # publishOffer returns {listingId, offers:[{offerId}]}; capture the offer too.
    offers = response_body.get("offers")
    if isinstance(offers, list) and offer_id is None:
        for entry in offers:
            if isinstance(entry, dict) and entry.get("offerId"):
                offer_id = entry["offerId"]
                break

    base_dir = _ledger_base_dir(context)
    ledger = _load_or_create_ledger(context.test_run_id or "", base_dir=base_dir)
    if sku:
        ledger.add_test_sku(sku)
    if offer_id:
        ledger.add_offer(offer_id)
    if listing_id:
        ledger.add_listing(listing_id)
    ledger.add_event(RunEvent(
        operation=operation.key,
        timestamp=_now_iso(),
        status=status,
        sku=sku, offer_id=offer_id, listing_id=listing_id,
        request_id=request_id, trace_id=trace_id,
    ))
    save_ledger(ledger, base_dir=base_dir)


def _append_cleanup_event(
    ledger, operation: OperationRecord, status: int | None, record_id: str,
    *, sku: str | None = None, request_id: str | None = None,
) -> None:
    """Append a cleanup event to an in-memory ledger; the caller persists.

    ``test-run execute --cleanup`` calls SDK resources directly (bypassing the
    dispatch auto-recorder), so it records its withdraw/delete mutations here on
    the in-memory ledger and persists once at the end — otherwise the event
    stream would lose the cleanup half of the lifecycle.
    """
    if operation.key not in _RECORDABLE_MUTATIONS:
        return
    from .ledger import RunEvent

    offer_id = record_id if operation.key in {
        "sell_inventory.withdrawOffer", "sell_inventory.deleteOffer"
    } else None
    sku_id = record_id if operation.key == "sell_inventory.deleteInventoryItem" else sku
    ledger.add_event(RunEvent(
        operation=operation.key,
        timestamp=_now_iso(),
        status=status,
        sku=sku_id, offer_id=offer_id, listing_id=None,
        request_id=request_id, trace_id=None,
    ))


def _ledger_base_dir(context: CliContext):
    """The one resolved ledger directory (global ``--ledger-dir`` or default).

    Shared by auto-recording and the test-run commands so a custom directory can
    never split one run into two ledgers.
    """
    from pathlib import Path

    from .ledger import default_ledger_dir

    if context.ledger_dir:
        return Path(context.ledger_dir).expanduser()
    return default_ledger_dir()


def _load_or_create_ledger(run_id: str, *, base_dir=None):
    """Load a ledger, creating an empty one if it does not yet exist.

    Auto-recording previously degraded to a stderr warning per write when
    ``test-run init`` had not run first (``load_ledger`` raised). Creating the
    ledger here means a write command with ``--test-run-id`` always records,
    even on the first call of a run.
    """
    from datetime import UTC, datetime

    from .ledger import RunLedger, load_ledger, save_ledger

    try:
        return load_ledger(run_id, base_dir=base_dir)
    except FileNotFoundError:
        ledger = RunLedger(run_id=run_id, created_at=datetime.now(UTC).isoformat())
        save_ledger(ledger, base_dir=base_dir)
        return ledger


def _body_as_dict(body: Any) -> dict[str, Any]:
    """Coerce a request body (dict or Pydantic model) to a plain dict."""
    if isinstance(body, dict):
        return body
    try:
        from pydantic import BaseModel
    except ImportError:  # pragma: no cover
        return {}
    if isinstance(body, BaseModel):
        return body.model_dump(by_alias=True, exclude_none=True)
    return {}


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _request_id(response: httpx2.Response) -> str | None:
    """eBay's per-request id (either request-id header has been observed)."""
    return (
        response.headers.get("x-ebay-c-request-id")
        or response.headers.get("x-ebay-request-id")
    )


def _trace_id(response: httpx2.Response) -> str | None:
    """The traffic/edge trace id (``x-traffic-request-id``).

    Distinct from the per-request id: some eBay responses expose this edge
    trace header even when no ``x-ebay-*-request-id`` is present. Surfaced
    separately so the agent always has *some* traceability value.
    """
    return response.headers.get("x-traffic-request-id")


def _response_meta(operation: OperationRecord, response: httpx2.Response) -> dict[str, Any]:
    """Traceability envelope for --include-meta. No secrets, ever.

    ``request_id`` falls back to the traffic trace id when eBay did not return a
    dedicated request-id header, so the field is not ``null`` on responses that
    *do* carry a trace value. ``trace_id`` always exposes the
    raw traffic id when available.
    """
    request_id = _request_id(response)
    trace_id = _trace_id(response)
    return {
        "operation": operation.key,
        "http_method": operation.http_method,
        "path": operation.path,
        "status": response.status_code,
        "request_id": request_id or trace_id,
        "trace_id": trace_id,
    }


def _filter_headers(headers: httpx2.Headers) -> dict[str, str]:
    """Redact sensitive response headers in raw mode.

    Uses the same shared policy as dry-run so a raw response never echoes a
    token/cookie/signature header. The key is kept with a ``<redacted>`` marker
    for visibility, instead of the old behavior of dropping the header entirely.
    """
    return {
        key: ("<redacted>" if is_sensitive_name(key) else value)
        for key, value in headers.items()
    }


# ---------------------------------------------------------------------------
# Dry-run preview (spec §14.3): never sends a request, never acquires a token.
# ---------------------------------------------------------------------------

def _emit_dry_run(
    context: CliContext,
    operation: OperationRecord,
    service: ServiceRecord,
    path_params: dict[str, str],
    query_params: dict[str, Any],
    header_params: dict[str, str],
    body: Any,
    files: dict[str, Any],
) -> None:
    risk, reason = effective_risk(operation)
    rendered_path = operation.path
    for key, value in path_params.items():
        rendered_path = rendered_path.replace("{" + key + "}", str(value))
    preview: dict[str, Any] = {
        "dry_run": True,
        "operation": operation.key,
        "service": service.key,
        "http_method": operation.http_method,
        "url": f"{service.subdomain}://{service.base_path}{rendered_path}",
        "path": operation.path,
        "path_params": path_params,
        "query": redact_mapping(query_params),
        "headers": redact_mapping(header_params),
        # The SDK transport injects a default header set from config on
        # every request (Accept, marketplace id, and the Content/Accept-Language
        # the marketplace-locale derivation resolved). These do not appear under
        # ``headers`` (the explicit user/param headers) but they *will* be on the
        # wire, so we surface them explicitly to keep the preview truthful for an
        # agent comparing it to the actual HTTP request.
        "config_injected_headers": redact_mapping(_sdk_default_headers(context)),
        "request": _redact_body(operation, body, files),
        "marketplace": context.config.marketplace_id,
        # The resolved Content-Language determines whether an EBAY_DE
        # listing will validate; surfacing it in the preview makes the locale
        # workaround observable without the unknown-header escape hatch.
        "content_language": context.config.content_language,
        "accept_language": context.config.accept_language,
        "auth": {"scheme": operation.auth.scheme, "scopes": operation.auth.scopes},
        "signing": {
            "required": operation.signing.required,
            "reason": operation.signing.reason,
        },
        "risk": risk,
        "risk_reason": reason,
    }
    # --merge cannot fetch in dry-run (no network), so we annotate the
    # preview with what the read/merge/write would do instead of the body shape.
    if context.merge and is_replace_like(operation):
        preview["merge"] = (
            "--merge would GET the current state, apply the provided body over "
            "it, then PUT the merged result (not performed in --dry-run)."
        )
    emit_json(preview, pretty=context.pretty)


def _redact_body(operation: OperationRecord, body: Any, files: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {"kind": operation.request.kind}
    if operation.request.kind == "json":
        request["body_shape"] = _shape(_jsonify(body))
    elif operation.request.kind == "multipart":
        request["fields"] = {
            name: ("<file>" if isinstance(value, tuple) else value)
            for name, value in files.items()
        }
    elif operation.request.kind == "binary":
        request["bytes"] = len(body) if isinstance(body, bytes | bytearray) else None
    return request


def _shape(value: Any, depth: int = 0) -> Any:
    """A redacted structural preview: keys + leaf types, no values (spec §14.3)."""
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if is_sensitive_name(key)
                else _shape(val, depth + 1)
            )
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_shape(value[0], depth + 1)] if value else []
    if value is None:
        return None
    return type(value).__name__
