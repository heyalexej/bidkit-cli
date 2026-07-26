"""bidkit-cli: a command-line interface for the bidkit eBay SDK.

The CLI is a view over a generated operation manifest (see ``manifest.py``). It
exposes every generated OAS operation as both an ergonomic nested command
(``bidkit sell inventory get-inventory-items``) and a universal dispatcher
(``bidkit api call sell_inventory.getInventoryItems``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bidkit-cli")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.1.0"

__all__ = ["__version__"]
