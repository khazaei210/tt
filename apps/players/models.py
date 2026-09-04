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
