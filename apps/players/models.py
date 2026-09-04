from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Gender(models.TextChoices):
    MALE = "M", _("Male")
    FEMALE = "F", _("Female")


class Player(models.Model):
    """A player profile, distinct from a login (User) account.

    A Player can exist without ever logging in (e.g. entered by a
    tournament manager), and later be linked to a User account.
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
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("players:edit", kwargs={"pk": self.pk})


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
        super().save(*args, **kwargs)
