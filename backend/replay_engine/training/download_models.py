"""Install a verified model bundle from a local directory.

Example::

    python -m training.download_models --source releases/v2 \
        --releases model/artifacts/releases --version v2 --activate

The source may be a bundle directory or its manifest file.  Network/archive
download can be layered on top of this command; verification and activation
remain the same.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .model_bundle import ModelBundleStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="local model bundle directory or manifest")
    parser.add_argument("--releases", type=Path, default=Path("model/artifacts/releases"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--activate", action="store_true", help="make the staged release current")
    parser.add_argument("--require-checksums", action="store_true")
    args = parser.parse_args()

    store = ModelBundleStore(args.releases)
    staged = store.stage(args.source, version=args.version, require_checksums=args.require_checksums)
    print(f"staged model bundle: {staged}")
    if args.activate:
        active = store.activate(args.version, require_checksums=args.require_checksums)
        print(f"active model bundle: {active}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
