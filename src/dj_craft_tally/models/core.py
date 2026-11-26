"""Core domain models for workshop inventory and projects."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MONEY_DECIMAL_PLACES = 2
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class Workshop(models.Model):
    """A shared workshop that owns inventory, equipment, and projects."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("Workshop")
        verbose_name_plural = _("Workshops")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class WorkshopMembership(models.Model):
    """A user's role in a workshop, using the host project's user model."""

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MEMBER = "member", _("Member")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="crafttally_workshop_memberships",
    )
    role = models.CharField(max_length=16, choices=Role, default=Role.MEMBER)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("Workshop membership")
        verbose_name_plural = _("Workshop memberships")
        db_table = "crafttally_workshop_membership"
        ordering = ("workshop", "user")
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "user"], name="unique_workshop_membership"
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} in {self.workshop}"


class Unit(models.Model):
    """A global unit of measure used for inventory and outputs.

    ``base_unit`` identifies the unit used by ``scale_to_base``. Base units
    refer to themselves and have a scale of one. For example, kilograms have
    grams as their base and a scale of ``1000``. A null base is unspecified.
    """

    class Dimension(models.TextChoices):
        COUNT = "count", _("Count")
        MASS = "mass", _("Mass")
        VOLUME = "volume", _("Volume")
        LENGTH = "length", _("Length")
        AREA = "area", _("Area")
        TIME = "time", _("Time")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    code = models.CharField(
        max_length=32,
        unique=True,
        help_text=_("A stable identifier, such as g, mL, or item."),
    )
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=16)
    dimension = models.CharField(max_length=16, choices=Dimension)
    base_unit = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="derived_units",
        null=True,
        blank=True,
        help_text=_("Unit in which the conversion scale is expressed, if known."),
    )
    display_decimal_places = models.PositiveSmallIntegerField(
        default=2,
        validators=[MaxValueValidator(QUANTITY_DECIMAL_PLACES)],
        help_text=_("Decimal places used when displaying quantities in this unit."),
    )
    scale_to_base = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        default=Decimal("1"),
        validators=[
            MinValueValidator(Decimal("0.000001")),
            MaxValueValidator(MAX_SCALE_TO_BASE),
        ],
        help_text=_("How many base units this unit represents within its dimension."),
    )

    class Meta:
        verbose_name = _("Unit")
        verbose_name_plural = _("Units")
        ordering = ("dimension", "scale_to_base", "name")
        constraints = (
            models.CheckConstraint(
                condition=models.Q(display_decimal_places__lte=QUANTITY_DECIMAL_PLACES),
                name="unit_display_decimal_places_within_range",
            ),
            models.UniqueConstraint(
                fields=["dimension", "symbol"], name="unique_unit_dimension_symbol"
            ),
            models.CheckConstraint(
                condition=models.Q(scale_to_base__lte=MAX_SCALE_TO_BASE),
                name="unit_scale_to_base_within_range",
            ),
        )

    def __str__(self) -> str:
        return self.symbol

    def clean(self):
        super().clean()
        if not self.base_unit_id:
            return
        if self.base_unit_id == self.pk:
            if self.scale_to_base != Decimal("1"):
                raise ValidationError(
                    {"scale_to_base": _("A base unit must have a scale of 1.")}
                )
            return
        base = self.base_unit
        if base.dimension != self.dimension:
            raise ValidationError(
                {"base_unit": _("The base unit must have the same dimension.")}
            )
        if base.base_unit_id != base.pk or base.scale_to_base != Decimal("1"):
            raise ValidationError(
                {
                    "base_unit": _(
                        "The base unit must refer to itself and have a scale of 1."
                    )
                }
            )


class Currency(models.Model):
    """A currency and its display convention for monetary values."""

    class SymbolPosition(models.TextChoices):
        PREFIX = "prefix", _("Prefix")
        SUFFIX = "suffix", _("Suffix")

    code = models.CharField(primary_key=True, max_length=3)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    symbol_position = models.CharField(
        max_length=6, choices=SymbolPosition.choices, default=SymbolPosition.PREFIX
    )

    class Meta:
        verbose_name_plural = _("Currencies")
        db_table = "crafttally_currency"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"
