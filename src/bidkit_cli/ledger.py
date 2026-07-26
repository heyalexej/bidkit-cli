"""Durable test-run ledger and cleanup/financial-residue report.

Deleting an inventory item or offer cannot reverse a fee eBay has already
booked, and an agent that only remembers the records it created can miss a
second offer, a listing id, or an account charge from a previous cycle. The
ledger maps every test run to its source SKUs, generated SKUs, offers, listing
ids, request/trace ids, and observed finance references, then produces a final
report that distinguishes:

* ``seller_records_deleted`` — every recorded SKU/offer is gone on the seller API;
* ``frontend_converged`` — every recorded listing id is gone from the public/
  Browse representation (or honestly ``stale_after_delete``);
* ``financially_reversible`` — always False: record deletion never reverses a
  booked fee, and any observed finance reference is surfaced explicitly.

The ledger is a plain JSON file so it survives process restarts and can be
audited by hand. It never auto-deletes anything; it only records and reports.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Cleanup outcome states recorded on the ledger as the run progresses.
CLEANUP_PENDING = "pending"
CLEANUP_IN_PROGRESS = "in_progress"
CLEANUP_SELLER_DELETED = "seller_deleted"
CLEANUP_COMPLETE = "complete"

# Finance-observation status: record deletion never reverses
# a fee eBay has already booked, so cleanup must report an *observation*, not a
# guarantee. ``not_checked`` is the default; the cleanup flow sets
# ``no_charge_observed`` after a finance read returns nothing for the run, or
# ``charge_observed`` when a charge is seen (and surfaced in finance_refs).
FINANCE_NOT_CHECKED = "not_checked"
FINANCE_NO_CHARGE = "no_charge_observed"
FINANCE_CHARGE = "charge_observed"


def new_run_id() -> str:
    """A short, unique,sortable run id (timestamp + random suffix)."""
    return f"run-{int(time.time())}-{secrets.token_hex(3)}"


@dataclass
class RunEvent:
    """One durable event in a test run's append-only stream.

    Recorded automatically by dispatch when ``--test-run-id`` is present so that
    a crash between publish and the explicit ``record`` step cannot lose the
    exact listing id needed for cleanup. Carries the operation, its HTTP status,
    the ids it produced (sku/offer_id/listing_id), and eBay's request/trace ids.
    """

    operation: str
    timestamp: str
    status: int | None = None
    sku: str | None = None
    offer_id: str | None = None
    listing_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    note: str | None = None


@dataclass
class TraceEntry:
    """One request/trace id captured during the run for support/debugging."""

    operation: str
    timestamp: str
    request_id: str | None = None
    trace_id: str | None = None
    note: str | None = None


@dataclass
class FinanceRef:
    """A finance transaction observed for the run (fees are irreversible)."""

    timestamp: str
    transaction_type: str | None = None
    amount: str | None = None
    currency: str | None = None
    listing_id: str | None = None
    transaction_id: str | None = None


@dataclass
class RunLedger:
    """The durable record of one controlled test run."""

    run_id: str
    created_at: str
    source_skus: list[str] = field(default_factory=list)
    test_skus: list[str] = field(default_factory=list)
    offer_ids: list[str] = field(default_factory=list)
    listing_ids: list[str] = field(default_factory=list)
    traces: list[TraceEntry] = field(default_factory=list)
    finance_refs: list[FinanceRef] = field(default_factory=list)
    # Append-only event stream + finance-observation status.
    events: list[RunEvent] = field(default_factory=list)
    finance_status: str = FINANCE_NOT_CHECKED
    cleanup_status: str = CLEANUP_PENDING
    notes: list[str] = field(default_factory=list)

    def add_test_sku(self, sku: str) -> None:
        if sku and sku not in self.test_skus:
            self.test_skus.append(sku)

    def add_offer(self, offer_id: str) -> None:
        if offer_id and offer_id not in self.offer_ids:
            self.offer_ids.append(offer_id)

    def add_listing(self, listing_id: str) -> None:
        if listing_id and listing_id not in self.listing_ids:
            self.listing_ids.append(listing_id)

    def add_trace(self, entry: TraceEntry) -> None:
        self.traces.append(entry)

    def add_finance(self, ref: FinanceRef) -> None:
        self.finance_refs.append(ref)
        # Observing a charge flips the finance status; it is never reset by a
        # later delete (fees are irreversible).
        self.finance_status = FINANCE_CHARGE

    def add_event(self, event: RunEvent) -> None:
        """Append a durable event. Dedup is the caller's responsibility."""
        self.events.append(event)

    def record_finance_status(self, status: str) -> None:
        """Set the finance-observation status without downgrading past charges."""
        if self.finance_status == FINANCE_CHARGE:
            return  # a charge observed earlier stays observed
        self.finance_status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_ledger_dir() -> Path:
    """Where ledgers live unless ``--ledger-file`` overrides it."""
    import os

    cache_home = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(cache_home).expanduser() / "bidkit" / "test-runs"


def ledger_path_for(run_id: str, *, base_dir: Path | None = None) -> Path:
    base = base_dir or default_ledger_dir()
    return base / f"{run_id}.json"


def save_ledger(ledger: RunLedger, *, base_dir: Path | None = None) -> Path:
    """Persist a ledger atomically; returns the written path."""
    path = ledger_path_for(ledger.run_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger.to_dict(), indent=2, sort_keys=True))
    tmp.replace(path)
    return path


def load_ledger(run_id: str, *, base_dir: Path | None = None) -> RunLedger:
    """Load and validate a ledger; raises FileNotFoundError if absent."""
    path = ledger_path_for(run_id, base_dir=base_dir)
    return _ledger_from_dict(json.loads(path.read_text()))


def list_ledgers(*, base_dir: Path | None = None) -> list[Path]:
    base = base_dir or default_ledger_dir()
    if not base.exists():
        return []
    return sorted(base.glob("*.json"))


def _ledger_from_dict(data: dict[str, Any]) -> RunLedger:
    """Reconstruct a RunLedger, tolerating older files without every field."""
    traces = [TraceEntry(**t) for t in data.get("traces", [])]
    finance = [FinanceRef(**f) for f in data.get("finance_refs", [])]
    events = [RunEvent(**e) for e in data.get("events", [])]
    return RunLedger(
        run_id=data["run_id"],
        created_at=data["created_at"],
        source_skus=list(data.get("source_skus", [])),
        test_skus=list(data.get("test_skus", [])),
        offer_ids=list(data.get("offer_ids", [])),
        listing_ids=list(data.get("listing_ids", [])),
        traces=traces,
        finance_refs=finance,
        events=events,
        finance_status=data.get("finance_status", FINANCE_NOT_CHECKED),
        cleanup_status=data.get("cleanup_status", CLEANUP_PENDING),
        notes=list(data.get("notes", [])),
    )


def cleanup_report(
    ledger: RunLedger,
    *,
    seller_state: dict[str, str],
    frontend_state: dict[str, str],
    public_listing_state: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compute the tri-state cleanup report.

    ``seller_state`` maps each recorded SKU and offer id to its seller-side
    state (``present``/``deleted``/``not_checked``); ``frontend_state`` maps each
    listing id to its public/Browse combined state (``not_found``/``visible``/
    ``not_listed``/``public_ended``/``stale_after_delete``/``blocked``/
    ``timeout``); ``public_listing_state`` optionally maps each listing id to the
    public-side classification (``active``/``ended``/``retained``/``not_found``/
    ``blocked``) so the report can name the distinction explicitly:
    seller-records-deleted vs public-record retained/ended vs frontend not-listed.

    The report never claims a fee is reversible: deletion cannot reverse a fee
    eBay has already booked, and the finance-observation status
    (``not_checked``/``no_charge_observed``/``charge_observed``) is surfaced as an
    observation, not a guarantee.
    """
    public_listing_state = public_listing_state or {}
    seller_ids = [*ledger.test_skus, *ledger.offer_ids]
    seller_deleted = all(seller_state.get(sid) == "deleted" for sid in seller_ids)
    seller_records_remaining = [
        {"id": sid, "state": seller_state.get(sid, "not_checked")}
        for sid in seller_ids
        if seller_state.get(sid) != "deleted"
    ]

    # A listing is "converged" for cleanup when it is gone publicly (not_found)
    # OR the seller record is deleted and the public side is ended/retained/
    # still-active-looking-but-seller-gone (not_listed / public_ended /
    # stale_after_delete). A visibly ACTIVE public record whose seller side is
    # also present is NOT converged.
    converged_states = {"not_found", "not_listed", "public_ended", "stale_after_delete"}
    frontend_converged = all(
        frontend_state.get(lid) in converged_states for lid in ledger.listing_ids
    ) if ledger.listing_ids else True

    def _public_record(lid: str) -> str:
        # Name whether the public Browse representation is retained.
        state = public_listing_state.get(lid) or frontend_state.get(lid, "not_checked")
        if state in {"retained", "ended"}:
            return "retained"
        if state in {"not_found", "not_listed"}:
            return "absent"
        return "present"

    frontend_remaining = [
        {"listing_id": lid,
         "state": frontend_state.get(lid, "not_checked"),
         "public_listing_state": public_listing_state.get(lid, "not_checked"),
         "public_record": _public_record(lid)}
        for lid in ledger.listing_ids
        if frontend_state.get(lid) not in converged_states
    ]
    per_listing = [
        {"listing_id": lid,
         "frontend_state": frontend_state.get(lid, "not_checked"),
         "public_listing_state": public_listing_state.get(lid, "not_checked"),
         "public_record": _public_record(lid)}
        for lid in ledger.listing_ids
    ]

    return {
        "run_id": ledger.run_id,
        "seller_records_deleted": seller_deleted and not seller_records_remaining,
        "frontend_converged": frontend_converged and not frontend_remaining,
        # Record deletion never reverses a fee eBay has already booked; this is
        # always False so a cleanup result can never read as "financially clean".
        "financially_reversible": False,
        "finance_status": ledger.finance_status,
        "records_remaining": seller_records_remaining,
        "frontend_remaining": frontend_remaining,
        "per_listing": per_listing,
        "finance_references": [asdict(f) for f in ledger.finance_refs],
        "finance_charges_observed": len(ledger.finance_refs),
        "events_recorded": len(ledger.events),
        "summary": _cleanup_summary(
            seller_deleted=seller_deleted and not seller_records_remaining,
            frontend_converged=frontend_converged and not frontend_remaining,
            charges=len(ledger.finance_refs),
            finance_status=ledger.finance_status,
        ),
    }


def _cleanup_summary(*, seller_deleted: bool, frontend_converged: bool,
                    charges: int, finance_status: str) -> str:
    parts: list[str] = []
    parts.append("seller records deleted" if seller_deleted else "seller records REMAIN")
    parts.append("frontend converged" if frontend_converged else "frontend NOT converged")
    parts.append(f"finance: {finance_status}")
    if charges:
        parts.append(f"{charges} finance charge(s) observed (irreversible)")
    return "; ".join(parts)


__all__ = [
    "CLEANUP_COMPLETE",
    "CLEANUP_IN_PROGRESS",
    "CLEANUP_PENDING",
    "CLEANUP_SELLER_DELETED",
    "FINANCE_CHARGE",
    "FINANCE_NO_CHARGE",
    "FINANCE_NOT_CHECKED",
    "FinanceRef",
    "RunEvent",
    "RunLedger",
    "TraceEntry",
    "cleanup_report",
    "default_ledger_dir",
    "ledger_path_for",
    "list_ledgers",
    "load_ledger",
    "new_run_id",
    "save_ledger",
]
