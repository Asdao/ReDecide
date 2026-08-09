from __future__ import annotations

import unittest

from backend.app.coach.intent_public_text import translate_provider_aliases


class TranslateProviderAliasesTests(unittest.TestCase):
    def test_translates_intent_token_case_insensitively(self) -> None:
        self.assertEqual(
            translate_provider_aliases(
                "PLAYER_INTENT differs from player_intent, but Player_Intent is subjective."
            ),
            "your stated intent differs from your stated intent, "
            "but your stated intent is subjective.",
        )

    def test_translates_player_aliases_to_consistent_public_phrases(self) -> None:
        self.assertEqual(
            translate_provider_aliases(
                "PLAYER_01 was near player_02; player_03 supported PLAYER_99."
            ),
            "the player was near the opponent; another player supported another player.",
        )

    def test_preserves_possessive_grammar(self) -> None:
        self.assertEqual(
            translate_provider_aliases("player_01's path crossed player_02's path."),
            "the player's path crossed the opponent's path.",
        )

    def test_does_not_partially_replace_longer_identifiers(self) -> None:
        text = (
            "player_010 player_01_backup xplayer_01 PLAYER_INTENTION "
            "my_PLAYER_INTENT_value"
        )
        self.assertEqual(translate_provider_aliases(text), text)

    def test_preserves_ordinary_words_and_punctuation(self) -> None:
        text = "The player's intent was unclear; player one moved normally."
        self.assertEqual(translate_provider_aliases(text), text)

    def test_translation_is_idempotent(self) -> None:
        translated = translate_provider_aliases(
            "PLAYER_INTENT: player_01 disengaged from player_02 with player_04 nearby."
        )
        self.assertEqual(translate_provider_aliases(translated), translated)

    def test_translates_unknown_two_digit_alias_without_exposing_it(self) -> None:
        self.assertEqual(
            translate_provider_aliases("player_00 was present."),
            "another player was present.",
        )


if __name__ == "__main__":
    unittest.main()
