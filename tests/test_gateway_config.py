import unittest
from unittest.mock import patch, ANY
from app.translation.openai_translator import OpenAITranslator


class TestGatewayConfig(unittest.TestCase):
    def test_json_wrapped_text_is_unwrapped_without_changing_plain_text(self):
        self.assertEqual(OpenAITranslator.normalize_translation('["বাংলা অনুবাদ"]'), "বাংলা অনুবাদ")
        self.assertEqual(OpenAITranslator.normalize_translation("[উদ্ধৃতি]"), "[উদ্ধৃতি]")
        self.assertEqual(OpenAITranslator.normalize_translation(["বাংলা"]), "বাংলা")

    @patch("app.translation.openai_translator.OpenAI")
    def test_custom_gateway_and_model_reach_client(self, client):
        translator = OpenAITranslator(api_key="test-placeholder", model="gateway-model", base_url="https://gateway.example/v1")
        client.assert_called_once_with(api_key="test-placeholder", base_url="https://gateway.example/v1", http_client=ANY)
        self.assertEqual(translator.model, "gateway-model")

    @patch("app.translation.openai_translator.OpenAI")
    def test_explicit_empty_endpoint_uses_sdk_default(self, client):
        OpenAITranslator(api_key="test-placeholder", base_url="")
        client.assert_called_once_with(api_key="test-placeholder", base_url=None, http_client=ANY)
