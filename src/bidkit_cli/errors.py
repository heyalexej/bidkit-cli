"""Stable exit codes and structured error reporting (spec §12).

All diagnostics go to stderr; successful data to stdout. Secrets are never
serialized: :class:`CliError` only carries operation keys, status, request ids,
and public remediation hints — never tokens, secrets, or Authorization headers.
"""

from __future__ import annotations

import sys
from typing import Any

import orjson

# Exit codes are part of the compatibility surface (spec §20).
EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_API = 4
EXIT_TRANSPORT = 5
EXIT_VALIDATION = 6
EXIT_SAFETY = 7
EXIT_IO = 8
EXIT_INTERNAL = 9


class CliError(Exception):
    """Base class for all errors raised intentionally by the CLI.

    ``kind`` is the stable machine-readable tag in JSON error output.
    """

    exit_code: int = EXIT_USAGE
    kind: str = "cli_error"

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        operation: str | None = None,
        request_id: str | None = None,
        details: list[Any] | None = None,
        hint: str | None = None,
        risk: str | None = None,
        classification: str | None = None,
        retryable: bool | None = None,
        retry_after: float | None = None,
        normalized_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.operation = operation
        self.request_id = request_id
        self.details = details
        self.hint = hint
        # Effective risk that triggered a safety refusal (read/write/
        # destructive/unknown). Populated by SafetyError; None for other errors.
        self.risk = risk
        # The stable machine-readable
        # classification (invalid_request/not_found/account_not_eligible/
        # capability_not_granted/upstream_error/rate_limited/transport_error)
        # plus whether the call is retryable and a bounded normalized body for
        # non-JSON (HTML) upstream errors. Surfaces in JSON error output so an
        # agent can decide retries/remediation deterministically.
        self.classification = classification
        self.retryable = retryable
        self.retry_after = retry_after
        self.normalized_body = normalized_body

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "message": self.message,
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.operation:
            payload["operation"] = self.operation
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.details:
            payload["details"] = self.details
        if self.hint:
            payload["hint"] = self.hint
        if self.risk:
            payload["risk"] = self.risk
        if self.classification:
            payload["classification"] = self.classification
        if self.retryable is not None:
            payload["retryable"] = self.retryable
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        if self.normalized_body is not None:
            payload["normalized_body"] = self.normalized_body
        return {"error": payload}


class UsageError(CliError):
    exit_code = EXIT_USAGE
    kind = "usage_error"


class ManifestError(CliError):
    exit_code = EXIT_USAGE
    kind = "manifest_error"


class ConfigError(CliError):
    exit_code = EXIT_CONFIG
    kind = "config_error"


class ApiError(CliError):
    exit_code = EXIT_API
    kind = "api_error"


class TransportError(CliError):
    exit_code = EXIT_TRANSPORT
    kind = "transport_error"


class ValidationError_(CliError):
    exit_code = EXIT_VALIDATION
    kind = "validation_error"


class SafetyError(CliError):
    exit_code = EXIT_SAFETY
    kind = "safety_error"


class IoError(CliError):
    exit_code = EXIT_IO
    kind = "io_error"


class InternalError(CliError):
    """An unexpected exception escaped to the entry point.

    Distinct kind and exit code so an internal fault is never mislabeled as the
    caller's mistake (exit 2) — an agent branching on exit codes must be able to
    tell "my request was wrong" from "the tool broke".
    """

    exit_code = EXIT_INTERNAL
    kind = "internal_error"


def report_error(err: CliError, *, json_mode: bool) -> int:
    """Print ``err`` to stderr in the selected shape and return its exit code."""
    stream = sys.stderr
    if json_mode:
        stream.write(orjson.dumps(err.as_dict(), option=orjson.OPT_INDENT_2).decode())
        stream.write("\n")
    else:
        parts = [f"error: {err.message}"]
        if err.operation:
            parts.append(f"  operation: {err.operation}")
        if err.status is not None:
            parts.append(f"  status: {err.status}")
        if err.request_id:
            parts.append(f"  request-id: {err.request_id}")
        # The stable taxonomy must reach an agent in text mode
        # too, not only in JSON. ``classification``/``retryable``/``retry_after``
        # are exactly what an agent needs to decide remediation.
        if err.classification:
            parts.append(f"  classification: {err.classification}")
        if err.retryable is not None:
            parts.append(f"  retryable: {err.retryable}")
        if err.retry_after is not None:
            parts.append(f"  retry_after: {err.retry_after}s")
        if err.hint:
            parts.append(f"  hint: {err.hint}")
        stream.write("\n".join(parts) + "\n")
    return err.exit_code
