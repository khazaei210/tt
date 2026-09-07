"""Long-polls Bale's getUpdates and dispatches each update to
apps.bale.services.handle_update — the mechanism that links a player's
Bale chat when they share their phone number (see apps/bale/services.py).

Runs as its own long-lived process/service (see docker-compose.yml's
bale-poller service) rather than a webhook: Bale requires HTTPS for
webhooks, and this project's prod stack doesn't have TLS in front of it
yet (see docker-compose.prod.yml), so polling is the only option that
works today without extra infrastructure.
"""

import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.bale.client import BaleAPIError, BaleClient
from apps.bale.services import handle_update

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 25
RETRY_DELAY_SECONDS = 5
UNCONFIGURED_RECHECK_SECONDS = 3600


class Command(BaseCommand):
    help = "Long-poll Bale getUpdates and dispatch updates until stopped (Ctrl+C)."

    def handle(self, *args, **options):
        if not settings.BALE_BOT_TOKEN:
            self.stdout.write(
                self.style.WARNING("BALE_BOT_TOKEN is not set — Bale messaging is disabled, not polling.")
            )
            # Stay up rather than exit non-zero, so a "restart: unless-stopped"
            # compose service doesn't loop-restart while this is unconfigured.
            while True:
                time.sleep(UNCONFIGURED_RECHECK_SECONDS)

        client = BaleClient()
        offset = 0
        self.stdout.write("Polling Bale for updates…")
        while True:
            try:
                updates = client.call("getUpdates", offset=offset, timeout=POLL_TIMEOUT_SECONDS, limit=100)
            except BaleAPIError as exc:
                self.stderr.write(f"getUpdates failed: {exc}")
                time.sleep(RETRY_DELAY_SECONDS)
                continue

            for update in updates or []:
                offset = update["update_id"] + 1
                try:
                    handle_update(update)
                except Exception:
                    logger.exception("Failed to handle Bale update %s", update.get("update_id"))
