"""
Environment and settings configuration.
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()


def get_env_config() -> Dict[str, Any]:
    """Retrieve environment variables for the agent runtime."""
    return {
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "harness_model_base_url": os.getenv("HARNESS_MODEL_BASE_URL", "https://api.deepseek.com"),
        "harness_model": os.getenv("HARNESS_MODEL", "deepseek-chat"),
        "coach_mode": os.getenv("REDECIDE_COACH_MODE", "http"),
        "analyses_per_player": int(os.getenv("REDECIDE_ANALYSES_PER_PLAYER", "10")),
    }
