import unittest

from ai_product_photo_sorter import setup_wizard


class OllamaSetupPersistenceTests(unittest.TestCase):
    def test_local_settings_are_written_to_env(self):
        text = setup_wizard.build_env_text(
            {
                "AI_PROVIDERS": "ollama,gemini",
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                "OLLAMA_MODEL": "gemma4:latest",
                "OLLAMA_KEEP_ALIVE": "15m",
                "OLLAMA_TIMEOUT": "600",
                "PRODUCT_SORTER_IMAGE_CACHE_ENTRIES": "32",
            }
        )
        self.assertIn("AI_PROVIDERS=ollama,gemini", text)
        self.assertIn("OLLAMA_BASE_URL=http://127.0.0.1:11434", text)
        self.assertIn("OLLAMA_MODEL=gemma4:latest", text)
        self.assertIn("OLLAMA_KEEP_ALIVE=15m", text)
        self.assertIn("OLLAMA_TIMEOUT=600", text)
        self.assertIn("PRODUCT_SORTER_IMAGE_CACHE_ENTRIES=32", text)


if __name__ == "__main__":
    unittest.main()
