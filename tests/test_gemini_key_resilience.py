import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sorter_core import call_gemini


class GeminiKeyResilienceTests(unittest.TestCase):
    def setUp(self):
        self.fake_types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)

    def test_service_disabled_key_is_removed_and_next_key_retries_batch(self):
        bad_models = MagicMock()
        bad_models.generate_content.side_effect = RuntimeError(
            "403 PERMISSION_DENIED: SERVICE_DISABLED "
            "generativelanguage.googleapis.com is disabled for this project"
        )
        good_models = MagicMock()
        good_models.generate_content.return_value = SimpleNamespace(
            text='{"items": []}', usage_metadata=None
        )
        bad_client = SimpleNamespace(models=bad_models)
        good_client = SimpleNamespace(models=good_models)

        class Pool:
            def __init__(self):
                self.clients = [bad_client, good_client]
                self.index = 0
                self.last_usage = {}
                self.last_model = ""
                self.model_aliases = {}

            @property
            def client(self):
                return self.clients[self.index]

        pool = Pool()
        with patch("sorter_core.types", self.fake_types):
            result = call_gemini(pool, "test-model", [], "", max_retries=0)

        self.assertEqual(result, {"items": []})
        self.assertEqual(bad_models.generate_content.call_count, 1)
        self.assertEqual(good_models.generate_content.call_count, 1)
        self.assertEqual(pool.clients, [good_client])
        self.assertIs(pool.client, good_client)

    def test_generic_permission_denied_is_not_blindly_rotated(self):
        denied_models = MagicMock()
        denied_models.generate_content.side_effect = RuntimeError(
            "403 PERMISSION_DENIED: caller lacks permission for this model"
        )
        untouched_client = SimpleNamespace(models=MagicMock())
        denied_client = SimpleNamespace(models=denied_models)

        class Pool:
            def __init__(self):
                self.clients = [denied_client, untouched_client]
                self.index = 0
                self.last_usage = {}
                self.last_model = ""
                self.model_aliases = {}

            @property
            def client(self):
                return self.clients[self.index]

        pool = Pool()
        with patch("sorter_core.types", self.fake_types):
            with self.assertRaisesRegex(RuntimeError, "cannot be retried"):
                call_gemini(pool, "test-model", [], "", max_retries=0)

        self.assertEqual(len(pool.clients), 2)
        self.assertEqual(pool.index, 0)
        untouched_client.models.generate_content.assert_not_called()

    def test_last_unusable_key_preserves_progress_and_requests_replacement(self):
        models = MagicMock()
        models.generate_content.side_effect = RuntimeError(
            "403 PERMISSION_DENIED: API_KEY_INVALID"
        )

        class Pool:
            def __init__(self):
                self.clients = [SimpleNamespace(models=models)]
                self.index = 0
                self.last_usage = {}
                self.last_model = ""
                self.model_aliases = {}

            @property
            def client(self):
                return self.clients[self.index]

        pool = Pool()
        with patch("sorter_core.types", self.fake_types), \
                patch("sorter_core.request_new_api_key", return_value="") as request_key:
            with self.assertRaisesRegex(RuntimeError, "All configured Gemini keys are unusable"):
                call_gemini(pool, "test-model", [], "", max_retries=0)

        request_key.assert_called_once()
        self.assertEqual(pool.clients, [])


if __name__ == "__main__":
    unittest.main()
