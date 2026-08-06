"""Vercel Services entrypoint for the unified FastAPI gateway."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _register_flattened_backend_package() -> None:
    """Expose the service root as ``backend`` in Vercel's function bundle.

    Local imports run from the repository root and naturally see the backend
    package. Vercel Services deploys ``backend/`` as the function root, placing
    this file at ``/var/task/main.py`` instead. Registering that directory as a
    package preserves the existing ``backend.*`` imports in both layouts.
    """

    if "backend" in sys.modules:
        return

    service_root = Path(__file__).resolve().parent
    package_init = service_root / "__init__.py"
    if not package_init.is_file():
        return

    spec = importlib.util.spec_from_file_location(
        "backend",
        package_init,
        submodule_search_locations=[str(service_root)],
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not register the Vercel backend package")

    package = importlib.util.module_from_spec(spec)
    sys.modules["backend"] = package
    spec.loader.exec_module(package)


_register_flattened_backend_package()

from backend.app.main import app

__all__ = ["app"]
