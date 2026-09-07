from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings

from apps.bale.client import BaleAPIError, BaleClient
from apps.bale.models import BaleSettings


@override_settings(BALE_BOT_TOKEN="test-token", BALE_API_BASE_URL="https://tapi.bale.ai", BALE_API_TIMEOUT=5)
class BaleClientTests(TestCase):
    def test_missing_token_raises_immediately(self):
        with self.assertRaises(BaleAPIError):
            BaleClient(token="")

    def test_successful_call_returns_result(self):
        response = Mock(json=Mock(return_value={"ok": True, "result": {"message_id": 1}}))
        with patch("apps.bale.client.requests.post", return_value=response) as mock_post:
            result = BaleClient().call("sendMessage", chat_id=123, text="hi")
        self.assertEqual(result, {"message_id": 1})
        called_url = mock_post.call_args.args[0]
        self.assertIn("bottest-token/sendMessage", called_url)

    def test_api_failure_raises_bale_api_error(self):
        response = Mock(json=Mock(return_value={"ok": False, "description": "chat not found"}))
        with patch("apps.bale.client.requests.post", return_value=response):
            with self.assertRaisesMessage(BaleAPIError, "chat not found"):
                BaleClient().call("sendMessage", chat_id=123, text="hi")

    def test_transport_error_raises_bale_api_error(self):
        with patch("apps.bale.client.requests.post", side_effect=requests.ConnectionError("boom")):
            with self.assertRaises(BaleAPIError):
                BaleClient().call("sendMessage", chat_id=123, text="hi")

    def test_non_json_response_raises_bale_api_error(self):
        response = Mock(json=Mock(side_effect=ValueError("no json")), status_code=502)
        with patch("apps.bale.client.requests.post", return_value=response):
            with self.assertRaises(BaleAPIError):
                BaleClient().call("sendMessage", chat_id=123, text="hi")

    def test_db_configured_token_takes_precedence_over_env_var(self):
        settings_obj = BaleSettings.get_solo()
        settings_obj.bot_token = "db-token"
        settings_obj.save()
        response = Mock(json=Mock(return_value={"ok": True, "result": {}}))
        with patch("apps.bale.client.requests.post", return_value=response) as mock_post:
            BaleClient().call("sendMessage", chat_id=123, text="hi")
        called_url = mock_post.call_args.args[0]
        self.assertIn("botdb-token/sendMessage", called_url)
