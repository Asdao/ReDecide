"""
Replay Extractor Tool for parsing .dem files and extracting telemetry.
"""

from typing import Dict, Any, Union
from pathlib import Path
from backend.app.replay.pipeline import extract_players_for_selector, stream_replay_pipeline


def parse_dem_replay(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Parse a CS2 demo replay file into telemetry features and decision moments."""
    return extract_players_for_selector(Path(file_path))


def process_replay_stream(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Process a replay stream and return the final pipeline payload."""
    last_payload = {}
    for progress in stream_replay_pipeline(Path(file_path)):
        if progress.get("stage") == "completed":
            last_payload = progress.get("result", {})
    return last_payload
