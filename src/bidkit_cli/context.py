"""Per-invocation context shared by every command.

Holds the resolved global options (output format, safety flags, dry-run, ...),
lazily-loaded manifest, and a single :class:`EbayClient` constructed only when a
command actually needs to hit the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from bidkit import EbayClient, EbayConfig, FileTokenCache

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

    _manifest: Manifest | None = field(default=None, repr=False)
    _client: EbayClient | None = field(default=None, repr=False)
    _config: EbayConfig | None = field(default=None, repr=False)

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

    # -- client --------------------------------------------------------------

    @property
    def client(self) -> EbayClient:
        """A single EbayClient per invocation, using a persistent token cache."""
        if self._client is None:
            cache = FileTokenCache(self.token_cache_path)
            self._client = EbayClient(self.config, token_cache=cache)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

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
