"""Deterministic public-text translations for intent coaching output.

Provider prompts use stable internal aliases so raw player identifiers never need
to reach the model.  Public coaching text should not expose those implementation
labels, so this module translates only complete, recognised alias tokens.
"""

from __future__ import annotations

import re
from re import Match


_PROVIDER_ALIAS = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:(?P<intent>PLAYER_INTENT)|player_(?P<player_number>\d{2}))"
    r"(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)


def translate_provider_aliases(text: str) -> str:
    """Replace complete provider-facing aliases with safe public phrases.

    Matching is case-insensitive and identifier-aware.  For example,
    ``player_01`` is translated but ``player_010`` and
    ``player_01_backup`` are preserved because they are not complete aliases.
    """

    def public_phrase(match: Match[str]) -> str:
        if match.group("intent") is not None:
            return "your stated intent"

        player_number = int(match.group("player_number"))
        if player_number == 1:
            # Third-person wording remains grammatical in constructions such as
            # "player_01 was moving" and "player_01's position".
            return "the player"
        if player_number == 2:
            return "the opponent"
        return "another player"

    return _PROVIDER_ALIAS.sub(public_phrase, text)


__all__ = ["translate_provider_aliases"]
