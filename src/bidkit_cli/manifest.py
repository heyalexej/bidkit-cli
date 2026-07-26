"""Load and validate the generated operation manifest.

The manifest (``generated/manifest.json``) is generated data produced by
``scripts/generate_openapi.py`` from the same normalized OpenAPI documents that
generate the Python client. This module is the CLI's only window onto the
operation surface: command trees, help, completion, schema inspection, and
dispatch all resolve through :class:`Manifest`.

The manifest ships in the wheel/sdist, so the installed CLI never needs the
original (copyrighted) OAS specs.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import orjson
from pydantic import BaseModel, Field

Risk = Literal["read", "write", "destructive", "unknown"]
ParamLocation = Literal["path", "query", "header"]
RequestKind = Literal["none", "json", "multipart", "binary"]
ResponseKind = Literal["json", "bytes", "text", "none"]


class ModelRef(BaseModel):
    """An importable ``module.attr`` reference to a generated Pydantic model.

    Resolved through :func:`import_model`, which only allows the
    ``bidkit.generated.models`` prefix — never arbitrary user-supplied paths.
    """

    model: str | None = None
    model_name: str | None = None

    @property
    def is_resolved(self) -> bool:
        return bool(self.model)

    def import_class(self) -> type[Any] | None:
        """Import and return the referenced model class, or None if untyped."""
        if not self.model:
            return None
        module_path, _, name = self.model.rpartition(".")
        if not module_path.startswith("bidkit.generated.models"):
            raise ValueError(f"refused to import non-allowlisted model path: {module_path}")
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, name)


class AuthRecord(BaseModel):
    scheme: str = "Bearer"
    security_schemes: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class SigningRecord(BaseModel):
    required: bool = False
    reason: str | None = None


class ParameterRecord(BaseModel):
    wire_name: str
    cli_name: str
    python_name: str
    location: ParamLocation
    required: bool = False
    type: str | None = None
    format: str | None = None
    enum: list[Any] | None = None
    is_array: bool = False
    description: str | None = None
    default: Any = None
    allow_repeated: bool = False


class MultipartField(BaseModel):
    name: str
    kind: Literal["file", "text"]
    required: bool = False


class RequestRecord(BaseModel):
    kind: RequestKind = "none"
    required: bool = False
    content_type: str | None = None
    model: str | None = None
    model_name: str | None = None
    accepts_mapping: bool = True
    fields: list[MultipartField] = Field(default_factory=list)

    @property
    def model_ref(self) -> ModelRef:
        return ModelRef(model=self.model, model_name=self.model_name)


class ResponseRecord(BaseModel):
    status: str
    content_type: str | None = None
    kind: ResponseKind = "none"
    model: str | None = None
    description: str | None = None

    @property
    def model_ref(self) -> ModelRef:
        return ModelRef(model=self.model, model_name=None)

    @property
    def success(self) -> bool:
        return self.status in {"200", "201", "202", "204", "206"}


class ExampleRecord(BaseModel):
    """A copy-pasteable ``bidkit`` invocation for one operation.

    Examples are generated metadata, not hand-written command logic: they are
    derived deterministically from an operation's parameters and effective risk
    (see ``bidkit_cli.examples``), with optional curated overrides for the few
    high-value operations that deserve a richer body. Every example records
    whether it is safe to run verbatim (``safe``) and whether its values are
    placeholders an agent must fill in (``illustrative``).
    """

    kind: Literal["command"] = "command"
    command: str
    safe: bool = True
    illustrative: bool = False
    note: str | None = None


class OperationRecord(BaseModel):
    key: str
    service_key: str
    namespace: str
    service_cli_name: str
    operation_id: str
    python_method: str
    aliases: list[str] = Field(default_factory=list)
    cli_path: list[str]
    http_method: str
    path: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    auth: AuthRecord = Field(default_factory=AuthRecord)
    signing: SigningRecord = Field(default_factory=SigningRecord)
    risk: Risk
    request: RequestRecord = Field(default_factory=RequestRecord)
    parameters: list[ParameterRecord] = Field(default_factory=list)
    responses: list[ResponseRecord] = Field(default_factory=list)
    stream_method: str | None = None
    # Generated + curated examples. Defaults to empty so the
    # bidkit generator can omit the field; ``Manifest.__init__`` fills it in
    # from ``bidkit_cli.examples`` so the generator patch never needs to learn
    # about examples.
    examples: list[ExampleRecord] = Field(default_factory=list)

    @property
    def path_params(self) -> list[ParameterRecord]:
        return [p for p in self.parameters if p.location == "path"]

    @property
    def query_params(self) -> list[ParameterRecord]:
        return [p for p in self.parameters if p.location == "query"]

    @property
    def header_params(self) -> list[ParameterRecord]:
        return [p for p in self.parameters if p.location == "header"]

    @property
    def required_params(self) -> list[ParameterRecord]:
        return [p for p in self.parameters if p.required]

    @property
    def success_response(self) -> ResponseRecord | None:
        for response in self.responses:
            if response.success:
                return response
        return None

    @property
    def success_responses(self) -> list[ResponseRecord]:
        """Every success response (200/201/202/204/206) in declared order.

        A generated operation can legitimately return several success statuses
        with different bodies (e.g. ``updateOffer`` returns 200 JSON *or* 204
        No Content). Surfacing all of them lets help/schema/examples describe
        what a caller can actually observe instead of only the first success in
        the OAS.
        """
        return [response for response in self.responses if response.success]

    @property
    def cli_name(self) -> str:
        """The kebab operation name, e.g. ``get-inventory-items``."""
        return self.cli_path[-1] if self.cli_path else self.operation_id


class ServiceRecord(BaseModel):
    key: str
    namespace: str
    cli_name: str
    python_accessor: str
    resource_class: str
    async_resource_class: str
    title: str
    version: str
    base_path: str
    subdomain: str
    auth_scheme: str = "Bearer"
    requires_signature: bool = False
    source_spec: str
    operations: list[str] = Field(default_factory=list)

    @property
    def cli_namespace(self) -> str:
        """post_order is exposed on the command line as ``post-order``."""
        return "post-order" if self.namespace == "post_order" else self.namespace


class ManifestData(BaseModel):
    schema_version: int
    sdk_package: str = "bidkit"
    sdk_version: str | None = None
    generator_version: str = ""
    operation_count: int
    service_count: int
    namespace_count: int
    namespaces: list[str]
    services: list[ServiceRecord]
    operations: list[OperationRecord]


class Manifest:
    """Validated, indexed view over the generated manifest.

    Lookups are O(1) and unambiguous: by canonical key, by CLI path, by
    operation-id-within-service, and by alias. Fuzzy/ambiguous matches are only
    ever used for *display* (search), never for execution.
    """

    def __init__(self, data: ManifestData) -> None:
        self.data = data
        self._by_key: dict[str, OperationRecord] = {op.key: op for op in data.operations}
        self._by_cli_path: dict[tuple[str, ...], OperationRecord] = {
            tuple(op.cli_path): op for op in data.operations
        }
        self._services_by_key: dict[str, ServiceRecord] = {
            svc.key: svc for svc in data.services
        }
        # CLI-side example enrichment: the bidkit generator
        # does not emit examples, so we attach them here from the deterministic
        # generator in ``bidkit_cli.examples`` (with curated overrides). This
        # keeps examples always in sync with the operation's parameters.
        from .examples import examples_for

        for op in data.operations:
            if not op.examples:
                op.examples = examples_for(op)
        # (service_key, operation_id-or-alias) -> operation. The universal
        # dispatcher resolves ``bidkit api call sell_inventory getInventoryItems``
        # and ``... sell_inventory get_inventory_items`` through this index.
        self._by_service_alias: dict[tuple[str, str], OperationRecord] = {}
        for op in data.operations:
            names = {op.operation_id, op.python_method, *op.aliases}
            for name in names:
                self._by_service_alias[(op.service_key, name)] = op

    # -- accessors -----------------------------------------------------------

    @property
    def operations(self) -> list[OperationRecord]:
        return self.data.operations

    @property
    def services(self) -> list[ServiceRecord]:
        return self.data.services

    @property
    def namespaces(self) -> list[str]:
        return self.data.namespaces

    def service(self, key: str) -> ServiceRecord:
        try:
            return self._services_by_key[key]
        except KeyError:
            raise KeyError(f"unknown service: {key}") from None

    def operations_for_service(self, service_key: str) -> list[OperationRecord]:
        return [op for op in self.data.operations if op.service_key == service_key]

    def operations_for_namespace(self, namespace: str) -> list[OperationRecord]:
        return [op for op in self.data.operations if op.namespace == namespace]

    def operations_for_cli_namespace(self, cli_namespace: str) -> list[OperationRecord]:
        raw = "post_order" if cli_namespace == "post-order" else cli_namespace
        return self.operations_for_namespace(raw)

    # -- resolution ----------------------------------------------------------

    def get(self, key: str) -> OperationRecord | None:
        return self._by_key.get(key)

    def get_by_cli_path(self, path: list[str] | tuple[str, ...]) -> OperationRecord | None:
        return self._by_cli_path.get(tuple(path))

    def resolve(self, identifier: str, *, service: str | None = None) -> OperationRecord:
        """Resolve an operation for *execution* (never fuzzy).

        Accepted forms:
          * canonical key  ``sell_inventory.getInventoryItems``
          * ``service operation_id``    ``sell_inventory getInventoryItems``
          * ``service python_method``   ``sell_inventory get_inventory_items``
          * a bare operation id/alias, only when globally unique
        """
        if "." in identifier and service is None:
            op = self._by_key.get(identifier)
            if op is not None:
                return op
            # allow ``namespace.cli_service op``? No — require canonical key here.
        if service is not None:
            op = self._by_service_alias.get((service, identifier))
            if op is not None:
                return op
            # `service` might itself be a canonical prefix ``sell_inventory``
            raise LookupError(
                f"no operation {identifier!r} in service {service!r}"
            ) from None
        # bare alias: only safe if globally unique
        matches = [
            op
            for op in self.data.operations
            if identifier
            in {op.operation_id, op.python_method, *op.aliases, op.key}
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise LookupError(f"no operation matches {identifier!r}")
        raise AmbiguousOperation(identifier, matches)

    def search(self, query: str) -> list[OperationRecord]:
        """Case-insensitive substring search across the discovery fields."""
        needle = query.lower()
        results = []
        for op in self.data.operations:
            haystack = " ".join(
                [
                    op.key,
                    op.operation_id,
                    op.python_method,
                    *op.tags,
                    op.path,
                    op.summary or "",
                ]
            ).lower()
            if needle in haystack:
                results.append(op)
        return results


class AmbiguousOperation(LookupError):
    def __init__(self, identifier: str, candidates: list[OperationRecord]) -> None:
        self.identifier = identifier
        self.candidates = candidates
        names = ", ".join(op.key for op in candidates[:10])
        super().__init__(
            f"{identifier!r} is ambiguous; matched {len(candidates)} operations: {names}"
        )


def _load_bytes() -> bytes:
    """Read the bundled manifest. Prefer an importlib.resources package read so a
    wheel install works without a source tree; fall back to a sibling file path
    for editable/source checkouts."""
    try:
        return resources.files("bidkit_cli.generated").joinpath("manifest.json").read_bytes()
    except (ModuleNotFoundError, FileNotFoundError, AttributeError):
        path = Path(__file__).resolve().parent / "generated" / "manifest.json"
        return path.read_bytes()


@lru_cache(maxsize=1)
def load_manifest() -> Manifest:
    """Parse and validate the generated manifest exactly once per process."""
    raw = orjson.loads(_load_bytes())
    data = ManifestData.model_validate(raw)
    _validate_cross_references(data)
    return Manifest(data)


# The CLI's command surface is generated from a specific bidkit generation
# snapshot. We support the same minor series the manifest was generated against;
# a future bidkit minor/major can rename methods/services and must be opted into
# deliberately (regenerate the manifest + bump the range).
def assert_sdk_compatible(manifest: Manifest) -> None:
    """Raise ConfigError if the installed bidkit generation differs from the manifest's.

    Compares the major.minor series, not the patch: a patch release that keeps
    the generated method names is fine; a minor/major change is not, even if it
    still satisfies the pip dependency range.
    """
    from .errors import ConfigError

    declared = manifest.data.sdk_version
    if not declared:
        return  # older manifest without the field; nothing to check
    installed = _installed_sdk_version()
    if installed is None:
        return  # bidkit not importable for a version read; let dispatch fail clearly
    if _major_minor(installed) != _major_minor(declared):
        raise ConfigError(
            f"bidkit {installed} is installed but the CLI manifest was generated "
            f"against bidkit {_major_minor(declared)}.x; the generated command "
            "surface can differ. Reinstall a compatible bidkit or regenerate the "
            "manifest against this bidkit (see packages/bidkit-cli/scripts/).",
        )


def _installed_sdk_version() -> str | None:
    try:
        import bidkit
    except ImportError:
        return None
    return getattr(bidkit, "__version__", None)


def _major_minor(version: str) -> tuple[int, int]:
    parts = version.split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return (-1, -1)


def _validate_cross_references(data: ManifestData) -> None:
    """Spec §18.2 invariants. Cheap to run once at load time; surfaces generator
    drift loudly instead of at a confusing dispatch failure."""
    service_keys = {svc.key for svc in data.services}
    op_keys: set[str] = set()
    cli_paths: set[tuple[str, ...]] = set()
    ops_by_service: dict[str, set[str]] = {}
    for op in data.operations:
        if op.service_key not in service_keys:
            raise ValueError(f"operation {op.key} references unknown service {op.service_key}")
        if op.key in op_keys:
            raise ValueError(f"duplicate operation key in manifest: {op.key}")
        op_keys.add(op.key)
        path = tuple(op.cli_path)
        if path in cli_paths:
            raise ValueError(f"duplicate CLI path in manifest: {' '.join(op.cli_path)}")
        cli_paths.add(path)
        ops_by_service.setdefault(op.service_key, set()).add(op.operation_id)
    for svc in data.services:
        declared = set(svc.operations)
        actual = ops_by_service.get(svc.key, set())
        missing = declared - actual
        if missing:
            raise ValueError(
                f"service {svc.key} lists operations not present in manifest: {sorted(missing)}"
            )
    if len(op_keys) != data.operation_count:
        raise ValueError(
            f"manifest operation_count={data.operation_count} but found {len(op_keys)} operations"
        )
