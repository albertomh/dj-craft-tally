"""Core domain models for workshop inventory and projects."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class Unit(models.Model):
    """A global unit of measure used for inventory and outputs.

    ``scale_to_base`` converts an entered quantity into its dimension's base
    unit. For example, kilograms have a scale of ``1000`` when grams are the
    mass base unit.
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
        ordering = ("dimension", "scale_to_base", "name")
        constraints = (
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
