class BaleNotLinkedError(Exception):
    """Raised by notify_player() when the target Player has no linked
    Bale chat yet (they haven't messaged the bot and shared their phone)."""
