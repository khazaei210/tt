from unittest.mock import call, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.bale.management.commands.bale_poll_updates import (
    POLL_HTTP_TIMEOUT_SECONDS,
    POLL_TIMEOUT_SECONDS,
)


class _StopLoop(Exception):
    """Raised by a mock to break the command's infinite while-loop for a test."""


class BalePollUpdatesCommandTests(TestCase):
    def test_poll_http_timeout_exceeds_poll_wait_timeout(self):
        # Regression: the client's own read timeout must be longer than
        # the long-poll "timeout" parameter sent to Bale, or every
        # getUpdates call aborts client-side before Bale can ever answer.
        self.assertGreater(POLL_HTTP_TIMEOUT_SECONDS, POLL_TIMEOUT_SECONDS)

    @override_settings(BALE_BOT_TOKEN="")
    def test_unconfigured_token_never_calls_the_api(self):
        with patch("apps.bale.management.commands.bale_poll_updates.time.sleep", side_effect=_StopLoop):
            with patch("apps.bale.management.commands.bale_poll_updates.BaleClient") as mock_client_cls:
                with self.assertRaises(_StopLoop):
                    call_command("bale_poll_updates")
        mock_client_cls.assert_not_called()

    @override_settings(BALE_BOT_TOKEN="test-token")
    def test_client_constructed_with_extended_timeout_and_dispatches_updates(self):
        update = {"update_id": 41, "message": {"chat": {"id": 1}, "text": "hi"}}
        with patch("apps.bale.management.commands.bale_poll_updates.handle_update") as mock_handle:
            with patch("apps.bale.management.commands.bale_poll_updates.BaleClient") as mock_client_cls:
                mock_client_cls.return_value.call.side_effect = [[update], _StopLoop()]
                with self.assertRaises(_StopLoop):
                    call_command("bale_poll_updates")

        # A fresh client is constructed each loop iteration (so a token
        # rotated via the web UI takes effect without a restart) — called
        # twice here since the side_effect list drives two iterations.
        mock_client_cls.assert_called_with(timeout=POLL_HTTP_TIMEOUT_SECONDS)
        self.assertEqual(mock_client_cls.call_count, 2)
        mock_handle.assert_called_once_with(update)
        # Second getUpdates call must acknowledge the first update via offset.
        self.assertEqual(
            mock_client_cls.return_value.call.call_args_list[1],
            call("getUpdates", offset=42, timeout=POLL_TIMEOUT_SECONDS, limit=100),
        )
