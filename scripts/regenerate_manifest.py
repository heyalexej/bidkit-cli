#!/usr/bin/env python3
"""Regenerate the CLI manifest from an explicit bidkit checkout.

This is the authoritative release path for the committed manifest. It does not
depend on a developer's dirty nested clone: it takes a clean bidkit source
checkout, applies the tracked generator patch, runs the generator pointed at
this package, and stamps the SDK version. A clean checkout of this repo plus a
clean bidkit checkout must reproduce the committed manifest byte-for-byte.

    python scripts/regenerate_manifest.py --bidkit-dir /path/to/bidkit

Exit code is non-zero if regeneration produces a manifest that differs from the
committed one (drift), which is exactly the CI gate we want.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

CLI_ROOT = Path(__file__).resolve().parent.parent
PATCH = CLI_ROOT / "patches" / "bidkit-manifest-generator.patch"
MANIFEST = CLI_ROOT / "src" / "bidkit_cli" / "generated" / "manifest.json"
ENRICH = CLI_ROOT / "scripts" / "enrich_manifest.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bidkit-dir", type=Path, required=True,
                        help="A bidkit source checkout to regenerate against.")
    parser.add_argument("--python", default=sys.executable,
                        help="Interpreter to run the bidkit generator with.")
    args = parser.parse_args()
    bidkit_dir = args.bidkit_dir.resolve()

    if not (bidkit_dir / "scripts" / "generate_openapi.py").exists():
        print(f"error: {bidkit_dir} does not look like a bidkit checkout", file=sys.stderr)
        return 2
    if not PATCH.exists():
        print(f"error: tracked patch not found at {PATCH}", file=sys.stderr)
        return 2

    # 1. Apply the generator patch (idempotent: skip if already applied).
    check = subprocess.run(
        ["git", "apply", "--check", "--reverse", str(PATCH)], cwd=bidkit_dir,
    )
    if check.returncode == 0:
        print("patch already applied; skipping")
    else:
        print(f"applying {PATCH.name} ...")
        apply = subprocess.run(["git", "apply", str(PATCH)], cwd=bidkit_dir)
        if apply.returncode != 0:
            print("error: failed to apply generator patch", file=sys.stderr)
            return apply.returncode

    # 2. Run the bidkit generator, pointed at this package's manifest dir.
    print("running bidkit generator ...")
    gen = subprocess.run(
        [
            args.python,
            "scripts/generate_openapi.py",
            "--spec-dir", "specs/ebay",
            "--package-dir", "src/bidkit",
            "--manifest-dir", str(MANIFEST.parent),
        ],
        cwd=bidkit_dir,
    )
    if gen.returncode != 0:
        return gen.returncode

    # 3. Stamp the SDK version (CLI-owned metadata, not emitted by the generator).
    print("stamping sdk_version ...")
    enrich = subprocess.run([args.python, str(ENRICH)], cwd=CLI_ROOT)
    if enrich.returncode != 0:
        return enrich.returncode

    # 4. Drift check: the regenerated manifest must match what was committed.
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", str(MANIFEST)],
        cwd=CLI_ROOT,
    )
    if diff.returncode == 0:
        print("manifest is up to date (no drift)")
        return 0
    print(
        "DRIFT: regenerated manifest differs from the committed one.\n"
        "Commit the regenerated manifest, or reconcile the generator patch.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
