from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .phone import normalize_mobile_number


class Gender(models.TextChoices):
    MALE = "M", _("Male")
    FEMALE = "F", _("Female")


class Player(models.Model):
    """A player profile, distinct from a login (User) account — kept
    separate rather than merged into a custom auth model because not
    every account is a player (referees, scorekeepers, tournament
    managers, admins) and a player-only field like mobile_number/gender
    would make no sense forced onto those.

    Every player is registered with a login and a mobile number together
    in one step (see players.forms.PlayerRegistrationForm /
    views.PlayerCreateView) — a Player can still be linked to an existing
    login separately afterward, or updated later by staff, but it always
    starts with one.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="player_profile",
        verbose_name=_("User account"),
    )
    first_name = models.CharField(_("First name"), max_length=100)
    last_name = models.CharField(_("Last name"), max_length=100)
    gender = models.CharField(_("Gender"), max_length=1, choices=Gender.choices)
    date_of_birth = models.DateField(_("Date of birth"), null=True, blank=True)
    club = models.CharField(_("Club"), max_length=150, blank=True)
    country = models.CharField(_("Country"), max_length=100, blank=True)
    mobile_number = models.CharField(
        _("Mobile number"),
        max_length=15,
        unique=True,
        help_text=_("Used to link this player's Bale chat for match notifications, e.g. 0912xxxxxxx."),
    )
    bale_chat_id = models.BigIntegerField(
        _("Bale chat ID"),
        null=True,
        blank=True,
        unique=True,
        editable=False,
        help_text=_("Set automatically once the player shares their phone number with the Bale bot."),
    )
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(mobile_number=""),
                name="player_mobile_number_required",
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("players:edit", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        self.mobile_number = normalize_mobile_number(self.mobile_number)
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if not is_new:
            self._sync_participant_display_names()

    def _sync_participant_display_names(self):
        """Tournament Participant rows cache this player's name in
        display_name (apps.tournaments.models.Participant.refresh_display_name)
        for query/ordering performance, rather than joining to Player on
        every match/standings render — so a rename here has to be pushed
        out explicitly, both to this player's own Individual participants
        and to any Doubles pair they're part of (DoublesPair.__str__
        includes both players' names)."""
        from apps.tournaments.models import Participant, ParticipantType

        Participant.objects.filter(
            participant_type=ParticipantType.INDIVIDUAL, individual_player=self, is_bye=False
        ).update(display_name=self.full_name)

        pairs = DoublesPair.objects.filter(models.Q(player_one=self) | models.Q(player_two=self))
        for pair in pairs:
            Participant.objects.filter(participant_type=ParticipantType.DOUBLES, doubles_pair=pair).update(
                display_name=str(pair)
            )


class DoublesPair(models.Model):
    """Two players paired for doubles competitions.

    A pair is reusable across tournaments/competitions, so it is its own
    entity rather than something created per-competition. player_one/
    player_two are stored in a canonical order (lowest pk first) so a pair
    can't be registered twice with the players swapped.
    """

    player_one = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="doubles_pairs_as_player_one")
    player_two = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="doubles_pairs_as_player_two")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["player_one__last_name", "player_two__last_name"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(player_one=models.F("player_two")),
                name="doubles_pair_distinct_players",
            ),
            models.UniqueConstraint(fields=["player_one", "player_two"], name="unique_doubles_pair"),
        ]

    def __str__(self):
        return f"{self.player_one.full_name} / {self.player_two.full_name}"

    def save(self, *args, **kwargs):
        if self.player_one_id and self.player_two_id and self.player_one_id > self.player_two_id:
            self.player_one_id, self.player_two_id = self.player_two_id, self.player_one_id
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if not is_new:
            from apps.tournaments.models import Participant, ParticipantType

            Participant.objects.filter(
                participant_type=ParticipantType.DOUBLES, doubles_pair=self, is_bye=False
            ).update(display_name=str(self))
