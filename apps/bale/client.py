"""Thin HTTP client for the Bale Bot API (https://docs.bale.ai/).

Everything Bale-specific below the level of "call this method with these
params" belongs in apps.bale.services, not here — this module only knows
how to reach the API and unwrap its response envelope. Never log the
full request URL: it embeds the bot token.
"""

import logging

import requests
from django.conf import settings

from .models import BaleSettings

logger = logging.getLogger(__name__)


class BaleAPIError(RuntimeError):
    """The request reached Bale but it reported failure, or a transport
    error (timeout, connection failure, malformed response) occurred."""


class BaleClient:
    def __init__(self, token=None, base_url=None, timeout=None):
        # Re-reads BaleSettings on every construction (not cached) so a
        # token/username saved from the web UI takes effect immediately —
        # including in the already-running bale-poller process — without
        # needing a restart.
        self.token = token if token is not None else BaleSettings.get_solo().effective_token
        self.base_url = (base_url if base_url is not None else settings.BALE_API_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.BALE_API_TIMEOUT
        if not self.token:
            raise BaleAPIError("BALE_BOT_TOKEN is not configured")

    def call(self, method, **params):
        url = f"{self.base_url}/bot{self.token}/{method}"
        try:
            response = requests.post(url, json=params, timeout=self.timeout)
        except requests.RequestException as exc:
            logger.warning("Bale API request to %s failed: %s", method, exc)
            raise BaleAPIError(f"{method} request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("Bale API %s returned a non-JSON response (status %s)", method, response.status_code)
            raise BaleAPIError(f"{method} returned a non-JSON response") from exc

        if not data.get("ok"):
            description = data.get("description") or f"{method} failed"
            logger.warning("Bale API %s failed: %s", method, description)
            raise BaleAPIError(description)
        return data.get("result")
