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

from django.core.management.base import BaseCommand

from apps.bale.client import BaleAPIError, BaleClient
from apps.bale.models import BaleSettings
from apps.bale.services import handle_update

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 25
# The HTTP client's own read timeout must be longer than the long-poll
# "timeout" parameter sent to Bale below — Bale holds the connection open
# for up to POLL_TIMEOUT_SECONDS waiting for a new update, so a client
# timeout equal to or shorter than that (e.g. the general-purpose
# BALE_API_TIMEOUT default) would abort every single call before Bale
# ever gets a chance to respond.
POLL_HTTP_TIMEOUT_SECONDS = POLL_TIMEOUT_SECONDS + 10
RETRY_DELAY_SECONDS = 5
UNCONFIGURED_RECHECK_SECONDS = 30


class Command(BaseCommand):
    help = "Long-poll Bale getUpdates and dispatch updates until stopped (Ctrl+C)."

    def handle(self, *args, **options):
        offset = 0
        warned_unconfigured = False
        self.stdout.write("Polling Bale for updates…")
        while True:
            if not BaleSettings.get_solo().effective_token:
                if not warned_unconfigured:
                    self.stdout.write(
                        self.style.WARNING("Bale bot token is not configured — waiting (checking periodically).")
                    )
                    warned_unconfigured = True
                time.sleep(UNCONFIGURED_RECHECK_SECONDS)
                continue
            warned_unconfigured = False

            # Constructed fresh every iteration (cheap — no network call)
            # rather than once outside the loop, so a token rotated from
            # the web UI (bale:settings) takes effect on the very next
            # poll without restarting this process.
            client = BaleClient(timeout=POLL_HTTP_TIMEOUT_SECONDS)
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
