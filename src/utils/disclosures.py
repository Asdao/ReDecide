"""
Garena AI Build Challenge 2026 - Third-Party Component & License Disclosures
"""

from typing import Dict, Any, List

GARENA_THIRD_PARTY_DISCLOSURES = {
  "challenge": "Garena AI Build Challenge 2026",
  "project_name": "RE:DECIDE",
  "submission_date": "2026-08-09",
  "components": [
    {
      "name": "FastAPI",
      "category": "Backend Framework",
      "license": "MIT",
      "usage": "REST API server for replay analysis, agent orchestration, and streaming progress"
    },
    {
      "name": "DeepSeek API / Pi Harness",
      "category": "LLM Provider",
      "license": "Commercial / API",
      "usage": "Generates outcome-blind tactical decision coaching from pre-decision telemetry evidence"
    },
    {
      "name": "Awpy",
      "category": "CS2 Parser & Replay Engine",
      "license": "MIT",
      "usage": "Extracts raw CS2 demo (.dem) telemetry events, positions, and damage windows"
    },
    {
      "name": "LightGBM",
      "category": "Machine Learning Model",
      "license": "MIT",
      "usage": "Win-chance probability estimation and spatial zone transition models"
    },
    {
      "name": "Next.js & React",
      "category": "Frontend Framework",
      "license": "MIT",
      "usage": "Interactive 2D radar visualization, timeline navigator, and intent coaching UI"
    },
    {
      "name": "Pydantic",
      "category": "Data Validation",
      "license": "MIT",
      "usage": "Type validation for API request/response contracts and pipeline schemas"
    }
  ]
}


def get_third_party_disclosures() -> Dict[str, Any]:
    """Return formal third-party library, API, and dataset disclosures for Garena judging."""
    return GARENA_THIRD_PARTY_DISCLOSURES
