"""Backward-compatible import path for :mod:`cs2_sim.core.model`.

New code should import models from ``cs2_sim.core.model``.  Keeping this
shim avoids breaking existing notebooks and downstream integrations.
"""

from cs2_sim.core.model import *  # noqa: F401,F403
from cs2_sim.core.model import __all__
