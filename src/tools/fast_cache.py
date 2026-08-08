"""
Fast In-Memory Cache and LRU Telemetry Engine for sub-millisecond inference latency.
"""

from functools import lru_cache
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "public"
KNOWLEDGE_BASE_PATH = DATA_ROOT / "tactical_knowledge_base.json"


@lru_cache(maxsize=128)
def load_tactical_knowledge_base() -> Dict[str, Any]:
    """Cache tactical knowledge base in memory to avoid disk I/O latency."""
    if KNOWLEDGE_BASE_PATH.is_file():
        try:
            with KNOWLEDGE_BASE_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class FastInferenceEngine:
    """Sub-millisecond latency telemetry lookup and tactical decision cache."""

    _cache: Dict[str, Any] = {}

    @classmethod
    def get_cached_decision(cls, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve pre-computed decision metrics in <0.1ms."""
        return cls._cache.get(cache_key)

    @classmethod
    def set_cached_decision(cls, cache_key: str, value: Dict[str, Any]) -> None:
        """Store decision metrics in fast memory cache."""
        cls._cache[cache_key] = value

    @classmethod
    def lookup_zone_tactics(cls, map_name: str, zone_name: str) -> Dict[str, Any]:
        """Fast O(1) zone tactical query from cached knowledge base."""
        kb = load_tactical_knowledge_base()
        maps = kb.get("maps", {})
        map_data = maps.get(map_name, maps.get("de_mirage", {}))
        zones = map_data.get("zones", {})
        return zones.get(zone_name, {
            "optimal_defensive_angles": ["STANDARD_CROSSFIRE"],
            "utility_cues": ["FLASH_BEFORE_ENTRY"],
            "retake_difficulty": "MODERATE",
            "clutch_win_prob_1v1": 0.50
        })
