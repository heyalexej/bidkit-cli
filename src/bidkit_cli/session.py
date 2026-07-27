"""Per-invocation session log: an append-only JSONL trail of what the CLI did.

Every run opens one ``.jsonl`` file under the sessions base dir and appends a
small JSON object per interesting event (``invocation``, ``gate``, ``op``,
``error``, ``end``). The trail is what makes a run auditable and, crucially,
*reversible*: ``session_revert.build_plan`` replays it in reverse, substituting
each recorded mutation with a compensating counterpart drawn from
:data:`REVERSE_OPS`, so an agent that created ten offers can take them all down
without remembering each id.

Design constraints that shape this module:

* **Secrets never reach disk.** ``argv`` is scrubbed (``redact_argv``) and every
  body is walked key-by-key with the shared redaction policy before it is
  serialized; a final token-shaped-value sweep over the whole record is the
  belt-and-suspenders pass. A live token in a header or query would already be
  caught earlier; the sweep catches one hiding in an arbitrary string field.
* **Fail-open.** Recording is telemetry: a broken log must never break the
  operation it is observing. Each write is wrapped; the first failure emits one
  stderr line and disables the recorder for the rest of the invocation.
  ``BIDKIT_SESSION_STRICT=1`` flips this to re-raise for runs that would rather
  die than lose an audit trail.
* **Best-effort HTTP attempt capture.** The SDK retries below the CLI; the only
  vantage point that sees every transport attempt is the ``httpx2`` client the
  CLI constructs, so :class:`AttemptCollector` installs as ``httpx2`` event
  hooks rather than wrapping the SDK call.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from .redaction import is_sensitive_name, redact_mapping

__all__ = [
    "SCHEMA_VERSION",
    "IRREVERSIBLE",
    "REVERSE_OPS",
    "AttemptCollector",
    "NullRecorder",
    "ReverseSpec",
    "SessionRecorder",
    "irreversible_reason",
    "new_id",
    "redact_argv",
    "reverse_hint_for",
    "sessions_base_dir",
]

SCHEMA_VERSION: int = 1

# Bodies larger than this spill to a content-addressed blob so the JSONL trail
# stays cheap to grep and load; the inline record keeps a sha256 + ref pointer.
_BODY_SPILL_THRESHOLD = 2048

# Restrictive perms for PII at rest: only the owning user can read the trail.
_FILE_MODE = 0o600
_DIR_MODE = 0o700

_REDACTED = "<redacted>"

# Crockford base32 (no I/L/O/U): digits before letters, letters in ASCII order,
# so fixed-width big-endian encoding is lexicographically ordered. Required so
# ULID strings sort the same way as the (timestamp, random) tuples they encode.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Token-shape detectors for free-standing values. eBay user/app tokens look like
# ``v^1.1#i^1#f^0#...`` (a caret then later a hash); ``Bearer <opaque>`` is the
# other common shape. Both are masked wherever they appear so a token passed as
# a positional value or nested in a body can never reach the log.
_EBAY_TOKEN_RE = re.compile(r"\^.*#")
_BEARER_RE = re.compile(r"^Bearer\s+\S")


# ------------------------------------------------------------------------------------------------
# Base directory + identifiers
# ------------------------------------------------------------------------------------------------


def sessions_base_dir(override: str | None = None) -> Path:
    """Resolve the directory that holds all session JSONL files.

    Order: an explicit override, then ``BIDKIT_SESSIONS_DIR``, then
    ``$XDG_STATE_HOME/bidkit/sessions``, then
    ``~/.local/state/bidkit/sessions``. Values are ``expanduser``-ed so a
    literal ``~`` survives no further than this single resolution point.
    """
    if override:
        return Path(override).expanduser()
    env = os.environ.get("BIDKIT_SESSIONS_DIR")
    if env:
        return Path(env).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "bidkit" / "sessions"
    return Path("~/.local/state/bidkit/sessions").expanduser()


def _to_base32(value: int, length: int) -> str:
    """Fixed-width big-endian Crockford base32 of a non-negative integer."""
    chars = ["0"] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


# Per-process monotonic guard for ULID ordering. ULIDs are only sortable if two
# ids minted within the same millisecond keep a strictly increasing random
# suffix; without this guard, rapid consecutive calls would produce ids whose
# millisecond prefix ties and whose random suffix is unordered. The guard is
# self-contained (no other module reads or writes it) and is the unavoidable
# minimum state a monotonic ULID factory needs.
_MONOTONIC: list[int] = [0, 0]


def new_id() -> str:
    """A 26-char Crockford-base32 id: 10 chars ms timestamp + 16 chars random.

    Lexicographically increasing across calls: when two calls fall in the same
    millisecond the random suffix is incremented, and a clock that jumps
    backwards is pinned to the last-seen millisecond, so later ids always sort
    after earlier ones. The 48-bit ms prefix and 80-bit random suffix fit
    exactly into the 10+16 base32 chars.
    """
    ms = int(time.time() * 1000)
    last_ms, last_rand = _MONOTONIC[0], _MONOTONIC[1]
    if ms < last_ms:
        ms = last_ms  # defend against a clock stepping backwards
    rand = secrets.randbits(80)
    if ms == last_ms and rand <= last_rand:
        rand = last_rand + 1
    _MONOTONIC[0], _MONOTONIC[1] = ms, rand
    return _to_base32(ms, 10) + _to_base32(rand, 16)


# ------------------------------------------------------------------------------------------------
# Redaction of argv + arbitrary values
# ------------------------------------------------------------------------------------------------


def _looks_like_token(value: str) -> bool:
    """True if a free-standing string resembles a bearer/eBay token."""
    return bool(_BEARER_RE.match(value) or _EBAY_TOKEN_RE.search(value))


def redact_argv(argv: Sequence[str]) -> list[str]:
    """Return a copy of ``argv`` with secrets masked in place.

    Two surfaces are masked:

    * the value of any ``--token``-ish flag (name matches the shared sensitive
      policy), whether written ``--token VALUE`` or ``--token=VALUE``;
    * any positional/standalone argument that itself matches a bearer or eBay
      token shape, so a token pasted without its flag is still caught.
    """
    out: list[str] = []
    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if isinstance(arg, str) and arg.startswith("--") and "=" in arg:
            name, _eq, value = arg.partition("=")
            if is_sensitive_name(name.lstrip("-")) or _looks_like_token(value):
                out.append(f"{name}={_REDACTED}")
            else:
                out.append(arg)
            i += 1
            continue
        if (
            isinstance(arg, str)
            and arg.startswith("--")
            and is_sensitive_name(arg.lstrip("-"))
            and i + 1 < n
        ):
            out.append(arg)
            out.append(_REDACTED)
            i += 2
            continue
        if isinstance(arg, str) and _looks_like_token(arg):
            out.append(_REDACTED)
        else:
            out.append(arg)
        i += 1
    return out


def _redact_value(value: Any) -> Any:
    """Recursively replace sensitive values: by key name, or by token shape.

    Dict values under a sensitive key are masked wholesale; any string that
    looks like a token is masked regardless of where it sits, so a secret
    nested under a benign key still cannot leak. Idempotent: ``<redacted>``
    contains no token shape, so re-running the sweep is a no-op.
    """
    if isinstance(value, dict):
        return {
            k: (_REDACTED if is_sensitive_name(str(k)) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, str) and _looks_like_token(value):
        return _REDACTED
    return value


def _jsonable(value: Any) -> Any:
    """Normalize values orjson cannot encode natively (Path/datetime/models)."""
    # pydantic is a hard dependency of the SDK this CLI is built on, so it is
    # always importable; request/response bodies arrive as models routinely.
    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes | bytearray | memoryview):
        # Raw bytes anywhere in a record must not kill the recorder; a
        # placeholder keeps the record serializable.
        return {"binary": True, "size": len(bytes(value))}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _now_iso_ms() -> str:
    """UTC ISO-8601 timestamp with millisecond precision and a trailing ``Z``."""
    dt = datetime.now(UTC)
    return f"{dt:%Y-%m-%dT%H:%M:%S}.{dt.microsecond // 1000:03d}Z"


# ------------------------------------------------------------------------------------------------
# Reverse / irreversibility table
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReverseSpec:
    """A compensating operation plus the arg names needed to call it."""

    op: str
    args: tuple[str, ...]


# Curated v1 reverse table. Only mutations that have a clean, idempotent
# counterpart on the seller API are listed; everything else returns ``None``
# from :func:`reverse_hint_for` and is surfaced by the revert planner as a
# blocked step with a reason rather than silently dropped.
REVERSE_OPS: dict[str, ReverseSpec] = {
    "sell_inventory.createOrReplaceInventoryItem": ReverseSpec(
        "sell_inventory.deleteInventoryItem", ("sku",)
    ),
    "sell_inventory.createOffer": ReverseSpec(
        "sell_inventory.deleteOffer", ("offer_id",)
    ),
    "sell_inventory.createOrReplaceOffer": ReverseSpec(
        "sell_inventory.deleteOffer", ("offer_id",)
    ),
    "sell_inventory.publishOffer": ReverseSpec(
        "sell_inventory.withdrawOffer", ("offer_id",)
    ),
}

# Operations with no compensating action the tool will perform. Prefix entries
# are resolved in :func:`irreversible_reason` so the table does not have to list
# every generated ``sell_finances`` / ``sell_feedback`` op by hand.
IRREVERSIBLE: dict[str, str] = {
    "sell_inventory.bulkPublishOffer": "bulk publish must be withdrawn per offer",
    # Not a gap in the mapping: uploaded EPS images have no delete endpoint and
    # expire on their own, so "nothing to do" is the correct, complete answer.
    "commerce_media.createImageFromFile": (
        "uploaded EPS images expire on their own (~30 days); no cleanup exists or is needed"
    ),
    "commerce_media.createImageFromUrl": (
        "uploaded EPS images expire on their own (~30 days); no cleanup exists or is needed"
    ),
}

_FINANCES_REASON = "a booked fee cannot be reversed by deleting records"
_MESSAGE_REASON = "a sent message cannot be unsent"
_FEEDBACK_REASON = "left feedback cannot be withdrawn by API"


def reverse_hint_for(
    operation_key: str, *, ids: dict, params: dict
) -> dict[str, Any] | None:
    """Compensating op + resolved args for ``operation_key``, or ``None``.

    Args are filled from ``ids`` first (the ids the original op produced/used),
    then ``params`` (its request params). If a required arg is missing the hint
    is ``None`` — the revert planner then treats the op as blocked rather than
    emitting a half-formed compensating call.
    """
    spec = REVERSE_OPS.get(operation_key)
    if spec is None:
        return None
    resolved: dict[str, Any] = {}
    for name in spec.args:
        value = ids.get(name)
        if value is None:
            value = params.get(name)
        if value is None:
            return None
        resolved[name] = value
    return {"op": spec.op, "args": resolved}


def irreversible_reason(operation_key: str) -> str | None:
    """Human reason an op cannot be reversed, or ``None`` if it can be."""
    if operation_key in IRREVERSIBLE:
        return IRREVERSIBLE[operation_key]
    if operation_key.startswith("sell_finances."):
        return _FINANCES_REASON
    if operation_key.startswith("commerce_message.") and "send" in operation_key.lower():
        return _MESSAGE_REASON
    if operation_key.startswith("sell_feedback."):
        return _FEEDBACK_REASON
    return None


# ------------------------------------------------------------------------------------------------
# HTTP attempt capture (httpx2 event hooks)
# ------------------------------------------------------------------------------------------------


def _retry_info(response: Any) -> dict[str, Any] | None:
    """Best-effort retry hint from a response (``Retry-After`` when present)."""
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    retry_after = headers.get("retry-after")
    if not retry_after:
        return None
    try:
        return {"retry_after": int(float(retry_after))}
    except (TypeError, ValueError):
        return {"retry_after": str(retry_after)}


def _ebay_request_id(response: Any) -> str | None:
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    return headers.get("x-ebay-c-request-id") or headers.get("x-ebay-request-id")


def _public_attempt(entry: dict[str, Any]) -> dict[str, Any]:
    """Project an in-flight entry to the documented on-disk attempt shape."""
    return {
        "n": entry["n"],
        "status": entry["status"],
        "error": entry["error"],
        "elapsed_ms": entry["elapsed_ms"],
        "ebay_request_id": entry["ebay_request_id"],
        "quota": entry["quota"],
        "retry": entry["retry"],
    }


class AttemptCollector:
    """Captures one entry per HTTP attempt, including SDK-internal retries.

    Installed as ``httpx2`` event hooks on the client the CLI builds, because
    the SDK's retry loop is below the CLI: only the transport sees every
    attempt. Each SDK retry is a fresh ``client.send`` call, so the request
    hook fires once per attempt and the response hook closes it out; a
    transport error (no response) is closed out via :meth:`note_transport_error`.
    """

    def __init__(self) -> None:
        # Completed attempts, in attempt order. Drained by the recorder when it
        # emits the op record.
        self._attempts: list[dict[str, Any]] = []
        # Requests that have fired their request hook but not yet resolved.
        # httpx2's sync client is strictly sequential, so this holds at most one
        # entry at a time; we keep a small stack to be robust.
        self._pending: list[dict[str, Any]] = []

    def request_hook(self, request: Any) -> None:
        """``httpx2`` event_hooks["request"]: record the start of an attempt."""
        entry: dict[str, Any] = {
            "n": len(self._attempts) + len(self._pending) + 1,
            "status": None,
            "error": None,
            "elapsed_ms": 0,
            "ebay_request_id": None,
            "quota": None,
            "retry": None,
            "_start": time.monotonic(),
        }
        self._pending.append(entry)
        # Stash on the request so the response hook can correlate without
        # relying on ordering, then fall back to the pending stack if attribute
        # storage is unavailable.
        with contextlib.suppress(Exception):
            request._bidkit_attempt_entry = entry  # type: ignore[attr-defined]

    def response_hook(self, response: Any) -> None:
        """``httpx2`` event_hooks["response"]: close out the matching attempt."""
        request = getattr(response, "request", None)
        entry = getattr(request, "_bidkit_attempt_entry", None) if request else None
        if entry is None and self._pending:
            entry = self._pending[-1]
        if entry is None:
            return
        entry["status"] = getattr(response, "status_code", None)
        entry["elapsed_ms"] = int(round((time.monotonic() - entry["_start"]) * 1000))
        entry["ebay_request_id"] = _ebay_request_id(response)
        entry["retry"] = _retry_info(response)
        if entry in self._pending:
            self._pending.remove(entry)
        self._attempts.append(_public_attempt(entry))

    def note_transport_error(self, exc: BaseException) -> None:
        """Record that the most recent in-flight attempt failed to get a response."""
        if not self._pending:
            return
        entry = self._pending.pop()
        message = str(exc) if str(exc) else type(exc).__name__
        entry["error"] = f"{type(exc).__name__}: {message}"
        entry["elapsed_ms"] = int(round((time.monotonic() - entry["_start"]) * 1000))
        self._attempts.append(_public_attempt(entry))

    def drain(self) -> list[dict[str, Any]]:
        """Return and clear captured attempts (called when emitting an op record)."""
        out = self._attempts
        self._attempts = []
        self._pending = []
        return out


# ------------------------------------------------------------------------------------------------
# Session recorder
# ------------------------------------------------------------------------------------------------


def _session_id_from_filename(name: str) -> str:
    """Pull the trailing ``<session_id>`` out of ``<ts>_<session_id>.jsonl``."""
    stem = name[:-6] if name.endswith(".jsonl") else name
    return stem.rsplit("_", 1)[1] if "_" in stem else stem


def _resolve_append_path(base: Path, chosen: str | None) -> Path | None:
    """Find an existing session file to append to, or ``None`` for a new session.

    ``chosen`` may be a path to an existing file or a bare session id; a bare id
    is matched against ``<base>/*/*_<id>.jsonl``. A path-like value that does
    not exist is not silently treated as an id: we return ``None`` so the
    recorder starts a fresh session instead of appending to a phantom file.
    """
    if not chosen:
        return None
    candidate = Path(chosen).expanduser()
    if candidate.is_file():
        return candidate
    if os.sep in chosen or "/" in chosen or "\\" in chosen:
        return None
    matches = sorted(base.glob(f"*/*_{chosen}.jsonl"))
    return matches[0] if matches else None


class SessionRecorder:
    """Append-only JSONL recorder for one CLI invocation.

    One recorder per process invocation; all mutable state lives on the
    instance (no module-global recording state). Writes are fail-open: the
    first failure warns once to stderr and flips :attr:`enabled` to ``False``,
    after which every subsequent record is a no-op.
    """

    path: Path
    session_id: str
    invocation_id: str
    enabled: bool

    def __init__(
        self,
        path: Path,
        session_id: str,
        invocation_id: str,
        *,
        base: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.path = path
        self.session_id = session_id
        self.invocation_id = invocation_id
        self.enabled = enabled
        self._seq = 0
        self._warned = False
        # Track first-creation so perms are pinned exactly once. Re-chmodding
        # on every write would silently "repair" a dir the operator (or a test)
        # made restrictive, defeating fail-open.
        self._session_dir_ready = False
        self._session_file_ready = False
        self._start_monotonic = time.monotonic()
        # Base dir owns the bodies/ tree; fall back to two parents up from the
        # session file (<base>/<YYYY-MM>/<file>) when not told explicitly.
        self._base = base if base is not None else path.parent.parent
        self._collector = AttemptCollector()

    # -- lifecycle --------------------------------------------------------

    @classmethod
    def start(
        cls,
        *,
        base_dir: Path | None = None,
        session_id: str | None = None,
        invocation: dict[str, Any],
    ) -> SessionRecorder:
        """Open (or append to) a session file and write its ``invocation`` record.

        ``session_id`` wins over the ``BIDKIT_SESSION_ID`` env var. When either
        names an existing session file, the recorder appends to it — reusing
        its session id, minting a fresh invocation id, and restarting ``seq``
        at 0 — so a chained command extends the same trail instead of forking
        a new one.
        """
        base = sessions_base_dir(None if base_dir is None else str(base_dir))
        chosen = session_id or os.environ.get("BIDKIT_SESSION_ID")
        append_path = _resolve_append_path(base, chosen)
        if append_path is not None:
            sid = _session_id_from_filename(append_path.name)
            invid = new_id()
            path = append_path
        else:
            sid = chosen or new_id()
            invid = new_id()
            now = datetime.now(UTC)
            path = base / now.strftime("%Y-%m") / f"{now:%Y%m%d}T{now:%H%M%S}Z_{sid}.jsonl"
        self = cls(path, sid, invid, base=base, enabled=True)
        self._write_invocation(invocation)
        return self

    # -- public record methods -------------------------------------------

    def record_gate(self, **fields: Any) -> None:
        self._safe_write("gate", fields)

    def record_op(self, **fields: Any) -> None:
        self._safe_write("op", fields)

    def record_error(self, **fields: Any) -> None:
        self._safe_write("error", fields)

    def finish(self, exit_code: int) -> None:
        duration_ms = int(round((time.monotonic() - self._start_monotonic) * 1000))
        self._safe_write("end", {"exit_code": exit_code, "duration_ms": duration_ms})

    def attempts(self) -> AttemptCollector:
        return self._collector

    # -- writing ---------------------------------------------------------

    def _write_invocation(self, invocation: dict[str, Any]) -> None:
        fields = dict(invocation)
        argv = fields.get("argv")
        if isinstance(argv, list):
            fields["argv"] = redact_argv(argv)
        self._safe_write("invocation", fields)

    def _safe_write(self, record_type: str, fields: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            if record_type == "op":
                fields = self._process_bodies(fields)
            record = self._envelope(record_type, fields)
            # Normalize then redact the whole record. Redaction runs after
            # normalization so a pydantic body is a plain dict before the key
            # sweep, and the token-shape sweep covers every string field.
            record = _redact_value(_jsonable(record))
            line = orjson.dumps(record)
            self._append_bytes(line + b"\n")
            self._seq += 1
        except Exception as exc:  # noqa: BLE001 - fail-open catches everything
            self._fail(exc)

    def _envelope(self, record_type: str, fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "v": SCHEMA_VERSION,
            "type": record_type,
            "ts": _now_iso_ms(),
            "session_id": self.session_id,
            "invocation_id": self.invocation_id,
            "seq": self._seq,
            **fields,
        }

    def _fail(self, exc: BaseException) -> None:
        """Disable the recorder; re-raise in strict mode, warn once otherwise."""
        self.enabled = False
        if os.environ.get("BIDKIT_SESSION_STRICT") == "1":
            raise exc
        if not self._warned:
            self._warned = True
            sys.stderr.write(f"warning: session log unavailable: {exc}\n")
            sys.stderr.flush()

    def _append_bytes(self, data: bytes) -> None:
        """Append one record, creating dirs and pinning perms only on first use.

        Permissions are asserted when a path component is first created rather
        than on every write: re-asserting them each time would overwrite a dir
        the operator deliberately made restrictive and so mask a real failure.
        """
        if not self._session_dir_ready:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                os.chmod(self.path.parent, _DIR_MODE)
            self._session_dir_ready = True
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        if not self._session_file_ready:
            # A pre-existing file may carry looser perms from an older recorder.
            with contextlib.suppress(OSError):
                os.chmod(self.path, _FILE_MODE)
            self._session_file_ready = True

    # -- body spilling ---------------------------------------------------

    def _process_bodies(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Build/redact the ``request``/``response`` sub-records for an op.

        Accepts either raw ``request_body``/``request_params``/``response_body``
        (the natural shape for the dispatch integration) or pre-built
        ``request``/``response`` dicts whose ``body`` is re-spilled. Either way
        bodies are redacted, sha256-hashed, and spilled to a blob when large.
        """
        if isinstance(fields.get("request"), dict):
            fields["request"] = self._normalize_request(fields["request"])
        elif "request_body" in fields or "request_params" in fields:
            params = fields.pop("request_params", None)
            body = fields.pop("request_body", None)
            fields["request"] = self._build_request(params, body)

        if isinstance(fields.get("response"), dict):
            fields["response"] = self._spill_body(fields["response"].get("body"))
        elif "response_body" in fields:
            body = fields.pop("response_body", None)
            fields["response"] = self._spill_body(body)
        return fields

    def _build_request(self, params: Any, body: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            params = {}
        return {"params": redact_mapping(params), **self._spill_body(body)}

    def _normalize_request(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}
        return {"params": redact_mapping(params), **self._spill_body(request.get("body"))}

    def _spill_body(self, body: Any) -> dict[str, Any]:
        """Return ``{body, body_ref, body_sha256}`` for one request/response body.

        ``None`` (no body, e.g. a 204) yields all-``None``. Otherwise the body
        is normalized, redacted, and sha256-hashed; bodies whose serialized form
        exceeds the threshold spill to ``bodies/<ab>/<sha>.json`` and are
        referenced, while small bodies stay inline. ``body_sha256`` is always
        set when a body exists.
        """
        if body is None:
            return {"body": None, "body_ref": None, "body_sha256": None}
        if isinstance(body, bytes | bytearray | memoryview):
            # Binary uploads (e.g. Media uploadVideo) are hashed, never
            # serialized: the log stays JSON and the blob store stays small,
            # while the digest still content-addresses what was sent.
            raw = bytes(body)
            digest = hashlib.sha256(raw).hexdigest()
            return {
                "body": {"binary": True, "size": len(raw)},
                "body_ref": None,
                "body_sha256": digest,
            }
        redacted = _redact_value(_jsonable(body))
        data = orjson.dumps(redacted)
        digest = hashlib.sha256(data).hexdigest()
        if len(data) > _BODY_SPILL_THRESHOLD:
            blob_path = self._base / "bodies" / digest[:2] / f"{digest}.json"
            self._write_blob(blob_path, data)
            return {"body": None, "body_ref": str(blob_path), "body_sha256": digest}
        return {"body": redacted, "body_ref": None, "body_sha256": digest}

    def _write_blob(self, blob_path: Path, data: bytes) -> None:
        parent = blob_path.parent
        created_dir = not parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        if created_dir:
            with contextlib.suppress(OSError):
                os.chmod(parent, _DIR_MODE)
        # The blob is content-addressed and always ours: O_TRUNC + chmod is
        # safe even when it already exists (same content re-spilled).
        fd = os.open(blob_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        with contextlib.suppress(OSError):
            os.chmod(blob_path, _FILE_MODE)


class NullRecorder(SessionRecorder):
    """A disabled recorder used when session logging is turned off.

    Inherits the real record methods; they are no-ops because :attr:`enabled`
    is ``False`` from construction, so callers do not need to branch on the
    recorder kind. ``start`` skips all I/O so even a host with no writable
    state dir can run with logging disabled.
    """

    @classmethod
    def start(
        cls,
        *,
        base_dir: Path | None = None,
        session_id: str | None = None,
        invocation: dict[str, Any],
    ) -> NullRecorder:
        self = cls(Path(), "", "", enabled=False)
        return self
