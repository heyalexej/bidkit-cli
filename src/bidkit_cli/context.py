"""Per-invocation context shared by every command.

Holds the resolved global options (output format, safety flags, dry-run, ...),
lazily-loaded manifest, and a single :class:`EbayClient` constructed only when a
command actually needs to hit the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import httpx2
from bidkit import EbayClient, EbayConfig, FileTokenCache
from bidkit.config import DEFAULT_TIMEOUT

from .manifest import Manifest, load_manifest

OutputFormat = Literal["json", "table", "text", "raw"]
LogLevel = Literal["quiet", "warning", "info", "debug"]


@dataclass
class CliContext:
    """Threaded through Click as ``ctx.obj``."""

    config_path: str | None = None
    environment: str | None = None
    marketplace: str | None = None
    output_format: OutputFormat | None = None
    pretty: bool = True
    output_file: str | None = None
    timeout: float | None = None
    max_retries: int | None = None
    log_level: LogLevel = "warning"
    trace: bool = False
    no_color: bool = False
    allow_write: bool = False
    allow_write_expert: bool = False
    yes: bool = False
    dry_run: bool = False
    select: str | None = None
    force: bool = False
    # Wrap the JSON payload in {"meta": ..., "data": ...} so an agent can
    # preserve operation identity, status, and request id.
    include_meta: bool = False
    # Content/Accept-Language overrides + marketplace→locale derivation:
    # EBAY_DE listings need Content-Language: de-DE, which the
    # generated command does not expose. --merge turns a replace-like PUT into a
    # read/merge/write; --verify-live polls the API readback after a write
    # and reports "API updated; frontend not confirmed".
    content_language: str | None = None
    accept_language: str | None = None
    marketplace_locale: bool = False
    merge: bool = False
    verify_live: bool = False
    wait_for_live: float = 0.0
    # Controlled test-mode safety gate. When set, write ops
    # that carry a description must contain a test marker, scrambled provenance
    # must be explicitly consented to, and a run id is expected in description/
    # SKU for traceability. Engages ``testmode.preflight_test_mode`` in dispatch.
    test_mode: bool = False
    allow_scrambled_test_data: bool = False
    allow_untracked_test_run: bool = False
    test_marker: str | None = None
    test_run_id: str | None = None
    test_provenance: dict[str, str] | None = None
    # Directory for test-run ledger files. One resolved location shared by the
    # test-run commands AND dispatch's automatic event recording, so a custom
    # dir can never split one run into two ledgers.
    ledger_dir: str | None = None
    # Session audit log: one JSONL record (invocation/gate/op/error/end) per
    # invocation under ``sessions_dir``. Best-effort throughout — a recorder
    # fault can never change control flow or the exit code.
    session_log: bool = True
    sessions_dir: str | None = None
    session_id: str | None = None

    _manifest: Manifest | None = field(default=None, repr=False)
    _client: EbayClient | None = field(default=None, repr=False)
    _config: EbayConfig | None = field(default=None, repr=False)
    # The httpx2 client we inject into EbayClient (the SDK never closes a
    # caller-owned client, so we own its lifecycle in ``close``), and the lazily
    # built session recorder.
    _http: httpx2.Client | None = field(default=None, repr=False)
    _recorder: Any = field(default=None, repr=False)

    # -- manifest ------------------------------------------------------------

    @property
    def manifest(self) -> Manifest:
        if self._manifest is None:
            self._manifest = load_manifest()
        return self._manifest

    # -- configuration -------------------------------------------------------

    @property
    def config(self) -> EbayConfig:
        if self._config is None:
            from .config import load_effective_config

            self._config = load_effective_config(
                config_path=self.config_path,
                environment=self.environment,
                marketplace=self.marketplace,
                timeout=self.timeout,
                max_retries=self.max_retries,
                content_language=self.content_language,
                accept_language=self.accept_language,
                marketplace_locale=self.marketplace_locale,
            )
        return self._config

    @property
    def token_cache_path(self) -> str:
        """Absolute (user-expanded) path to the on-disk token cache.

        Expanded here, at the single source of truth, so every consumer —
        doctor's existence check, ``auth cache path``/``clear``, and the
        ``FileTokenCache`` handed to the client — operates on the same real
        file. A literal ``~`` in this value once made ``cache clear`` a silent
        no-op while the cache survived.
        """
        import os
        from pathlib import Path

        cache_home = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
        return str((Path(cache_home) / "bidkit" / "tokens.json").expanduser())

    # -- session recorder ---------------------------------------------------

    @property
    def recorder(self) -> Any:
        """The per-invocation SessionRecorder, built lazily on first use.

        Returns a real :class:`SessionRecorder` (appending to a session file)
        when ``session_log`` is True, or a no-op recorder when logging is
        disabled — or when the session module is unavailable / the recorder
        could not start. The session log is strictly best-effort, so this
        property never raises: a broken recorder must never block the CLI.
        """
        if self._recorder is None:
            self._recorder = self._build_recorder()
        return self._recorder

    def _build_recorder(self) -> Any:
        from pathlib import Path

        try:
            from .session import NullRecorder, SessionRecorder
        except ImportError:
            # session.py is authored by a parallel worker; until it lands (or
            # if it is ever removed) the CLI runs unchanged with a no-op recorder.
            return _NullRecorder()
        if not self.session_log:
            # NullRecorder.start would write nothing but still requires an
            # invocation payload; construct directly to skip that work.
            return NullRecorder(Path(), "", "", enabled=False)
        try:
            base_dir = Path(self.sessions_dir).expanduser() if self.sessions_dir else None
            return SessionRecorder.start(
                base_dir=base_dir,
                session_id=self.session_id,
                invocation=_build_invocation(self),
            )
        except Exception:  # noqa: BLE001 - fail open: never block the command
            return _NullRecorder()

    # -- client --------------------------------------------------------------

    @property
    def client(self) -> EbayClient:
        """A single EbayClient per invocation, using a persistent token cache.

        The httpx2 client is constructed here (rather than left to the SDK) so
        the session recorder's AttemptCollector can ride the request/response
        event hooks and observe every transport-level retry — the SDK's retry
        loop runs below this layer, so only the transport sees each attempt.
        The timeout mirrors exactly what the SDK would use (``config.timeout``
        or its ``DEFAULT_TIMEOUT``); because the client is now caller-owned,
        ``close`` closes it explicitly (the SDK never closes an injected client).
        """
        if self._client is None:
            cache = FileTokenCache(self.token_cache_path)
            collector = self.recorder.attempts()
            http = httpx2.Client(
                timeout=self.config.timeout or DEFAULT_TIMEOUT,
                event_hooks={
                    "request": [collector.request_hook],
                    "response": [collector.response_hook],
                },
            )
            self._http = http
            self._client = EbayClient(self.config, token_cache=cache, http_client=http)
        return self._client

    def close(self) -> None:
        import contextlib

        client = self._client
        injected_http = self._http
        self._client = None
        self._http = None
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()
        # The SDK never closes a caller-injected http client, so we own its
        # lifecycle here and close it ourselves.
        if injected_http is not None:
            with contextlib.suppress(Exception):
                injected_http.close()

    # -- output helpers ------------------------------------------------------

    @property
    def json_mode(self) -> bool:
        """Whether to emit machine-readable JSON to stdout.

        Defaults to JSON when stdout is not a TTY (automation-safe) and a table
        when interactive; an explicit --format always wins (spec §11.1).
        """
        if self.output_format is not None:
            return self.output_format == "json"
        import sys

        return not sys.stdout.isatty()

    @property
    def effective_format(self) -> OutputFormat:
        if self.output_format is not None:
            return self.output_format
        import sys

        return "table" if sys.stdout.isatty() else "json"

    def should_sign(self) -> bool:
        return self.trace


# ---------------------------------------------------------------------------
# Session-log fallback shims + invocation builder.
#
# These only run when ``bidkit_cli.session`` is unavailable (parallel
# development / a broken install) or when ``--no-session-log`` is set but the
# module is absent: the recorder/collector become no-ops so the injected httpx2
# client still installs hooks that simply record nothing. Keeping the CLI alive
# is the overriding requirement — the session log is strictly best-effort.
# ---------------------------------------------------------------------------


class _NullCollector:
    """No-op AttemptCollector: installed as httpx2 hooks that record nothing."""

    def request_hook(self, request: Any) -> None:
        ...

    def response_hook(self, response: Any) -> None:
        ...

    def note_transport_error(self, exc: BaseException) -> None:
        ...

    def drain(self) -> list[dict[str, Any]]:
        return []


class _NullRecorder:
    """No-op SessionRecorder used when logging is off or the module is absent."""

    enabled: bool = False
    path: Any = None
    session_id: Any = None
    invocation_id: Any = None

    def attempts(self) -> _NullCollector:
        return _NullCollector()

    def record_gate(self, **fields: Any) -> None:
        ...

    def record_op(self, **fields: Any) -> None:
        ...

    def record_error(self, **fields: Any) -> None:
        ...

    def finish(self, exit_code: int) -> None:
        ...


def _env_fingerprint() -> dict[str, Any]:
    """Runtime/version fingerprint for the invocation record.

    Tolerates a missing distribution (returns ``None``) so an editable/dev
    checkout without installed metadata still records a usable fingerprint and
    never raises.
    """
    import platform
    import sys
    from importlib.metadata import PackageNotFoundError, version

    def _ver(name: str) -> str | None:
        try:
            return version(name)
        except PackageNotFoundError:
            return None

    return {
        "cli_version": _ver("bidkit-cli"),
        "sdk_version": _ver("bidkit"),
        "httpx2_version": _ver("httpx2"),
        "python": sys.version,
        "platform": platform.platform(),
    }


def _build_invocation(context: CliContext) -> dict[str, Any]:
    """Build the CONTRACT ``invocation`` record payload for ``SessionRecorder.start``."""
    import os
    import sys

    from .session import redact_argv

    # Prefer explicit overrides; fall back to the already-loaded config without
    # forcing a load (the recorder may start before any command needs config).
    marketplace_id = context.marketplace
    if marketplace_id is None and context._config is not None:
        marketplace_id = context._config.marketplace_id
    environment = context.environment
    if environment is None and context._config is not None:
        environment = "sandbox" if context._config.sandbox else "production"

    return {
        "argv": redact_argv(sys.argv),
        "cwd": os.getcwd(),
        "env_fingerprint": _env_fingerprint(),
        "config_path": context.config_path,
        "environment": environment,
        "marketplace_id": marketplace_id,
        "test_run_id": context.test_run_id,
        "caller": os.environ.get("BIDKIT_CALLER"),
        "dry_run": context.dry_run,
        "parent_session_id": os.environ.get("BIDKIT_PARENT_SESSION_ID"),
    }
