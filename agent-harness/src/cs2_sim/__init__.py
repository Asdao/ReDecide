"""Harness-local package shim.

The simulator itself remains in the repository's ``src/cs2_sim`` package.  A
small namespace shim here lets the bridge be imported when the harness source
directory is placed before the repository source directory on ``PYTHONPATH``.
"""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

