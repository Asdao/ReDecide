"""
Replay Feature Vector and Embeddings Utilities.
"""

from typing import Dict, Any, List


class ReplayFeatureEmbeddings:
    """Extractor for player telemetry features into model vectors."""

    @staticmethod
    def extract_features(moment_data: Dict[str, Any]) -> List[float]:
        return [
            float(moment_data.get("time_seconds", 0.0)),
            float(moment_data.get("win_probability", 0.5)),
            float(moment_data.get("hp", 100)),
            float(1.0 if moment_data.get("has_bomb") else 0.0)
        ]
