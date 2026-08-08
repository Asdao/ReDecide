"""
LLM Client wrapper for DeepSeek and OpenAI-compatible API providers.
"""

from typing import Dict, Any, Optional
from backend.app.coach.pi_connector import generate_advice_with_pi_connector, generate_advice_with_http_adapter


class LLMClient:
    """Client for generating AI coaching explanations."""

    def __init__(self, mode: str = "http"):
        self.mode = mode

    def generate(self, prompt_payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.mode == "pi":
            return generate_advice_with_pi_connector(prompt_payload)
        return generate_advice_with_http_adapter(prompt_payload)
