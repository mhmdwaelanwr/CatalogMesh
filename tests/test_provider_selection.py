import os
import unittest
from unittest.mock import patch

from ai_product_photo_sorter.provider_selection import (
    ProviderSelectionError,
    canonical_provider_string,
    normalize_provider_environment,
    normalize_provider_sequence,
)


class ProviderSelectionTests(unittest.TestCase):
    def test_observed_gemeni_typo_is_corrected(self):
        providers, corrections = normalize_provider_sequence("gemeni")
        self.assertEqual(["gemini"], providers)
        self.assertEqual([("gemeni", "gemini")], corrections)

    def test_local_alias_maps_explicitly_to_ollama(self):
        providers, corrections = normalize_provider_sequence("local")
        self.assertEqual(["ollama"], providers)
        self.assertEqual([("local", "ollama")], corrections)

    def test_ollama_can_be_first_in_fallback_chain(self):
        providers, corrections = normalize_provider_sequence(
            " Ollama, GEMINI, openai, anthropic "
        )
        self.assertEqual(["ollama", "gemini", "openai", "anthropic"], providers)
        self.assertEqual([], corrections)

    def test_names_are_case_insensitive_deduplicated_and_ordered(self):
        providers, corrections = normalize_provider_sequence(
            " OpenAI, GEMINI, openai, anthropic "
        )
        self.assertEqual(["openai", "gemini", "anthropic"], providers)
        self.assertEqual([], corrections)

    def test_empty_selection_defaults_to_gemini(self):
        self.assertEqual((["gemini"], []), normalize_provider_sequence(""))

    def test_unknown_provider_fails_with_suggestion(self):
        with self.assertRaisesRegex(ProviderSelectionError, "Did you mean 'gemini'"):
            normalize_provider_sequence("gemnii")

    def test_canonical_string_is_safe_for_env(self):
        canonical, corrections = canonical_provider_string("local,gemeni,openai")
        self.assertEqual("ollama,gemini,openai", canonical)
        self.assertEqual([("local", "ollama"), ("gemeni", "gemini")], corrections)

    def test_environment_is_rewritten_to_canonical_values(self):
        with patch.dict(os.environ, {"AI_PROVIDERS": "local,gemeni,openai"}, clear=False):
            canonical = normalize_provider_environment(announce=False)
            self.assertEqual("ollama,gemini,openai", canonical)
            self.assertEqual("ollama,gemini,openai", os.environ["AI_PROVIDERS"])
            self.assertEqual("ollama", os.environ["AI_PROVIDER"])


if __name__ == "__main__":
    unittest.main()
