"""
Helper functions for serialization and dataset utilities.
"""

import json
from typing import Any, Dict


def serialize_payload(data: Any) -> str:
    """Serialize dictionary or list data to JSON string."""
    return json.dumps(data, indent=2, default=str)
