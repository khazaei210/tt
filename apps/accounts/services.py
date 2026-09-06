"""Give a Player a login (a User account), or reset one, from the app's own
UI (players:create_login/reset_password) — never public self-registration.

A generated password is returned in plain text exactly once, at creation
time, for the caller to hand to the staff member performing the action
(via a Django message) — it is never stored or logged anywhere.
"""

import secrets

from django.contrib.auth import get_user_model
from django.utils.text import slugify


class PlayerAlreadyHasLoginError(Exception):
    pass


class PlayerHasNoLoginError(Exception):
    pass


def suggest_username(player):
    """A reasonable starting username for the "create login" form — not
    guaranteed unique on its own; generate_unique_username() below handles
    that. allow_unicode keeps Persian names as-is rather than stripping
    them to nothing, since Django's User.username accepts unicode letters."""
    base = slugify(f"{player.first_name}{player.last_name}", allow_unicode=True)
    return base or f"player{player.pk}"


def _generate_unique_username(base):
    User = get_user_model()
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


def _generate_password():
    return secrets.token_urlsafe(12)


def create_player_login(player, *, username=None):
    """Create a User for this player and link it. Raises
    PlayerAlreadyHasLoginError if the player already has one — use
    reset_player_password() to issue that account a new password instead.

    Returns (user, raw_password) — raw_password is shown to the caller
    exactly once, it isn't retrievable afterward.
    """
    if player.user_id is not None:
        raise PlayerAlreadyHasLoginError(player)

    User = get_user_model()
    base_username = slugify(username, allow_unicode=True) if username else suggest_username(player)
    final_username = _generate_unique_username(base_username or f"player{player.pk}")
    raw_password = _generate_password()

    user = User.objects.create_user(username=final_username, password=raw_password)
    player.user = user
    player.save(update_fields=["user"])
    return user, raw_password


def reset_player_login_password(player):
    """Issue a fresh random password for a player's existing login.
    Raises PlayerHasNoLoginError if the player has no linked User yet.

    Returns raw_password — shown to the caller exactly once.
    """
    if player.user_id is None:
        raise PlayerHasNoLoginError(player)

    raw_password = _generate_password()
    player.user.set_password(raw_password)
    player.user.save(update_fields=["password"])
    return raw_password
