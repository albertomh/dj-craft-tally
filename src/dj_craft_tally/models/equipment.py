"""Core domain models for equipment."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7
from dj_craft_tally.models.core import Workshop

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MONEY_DECIMAL_PLACES = 2
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class Equipment(models.Model):
    """A workshop machine or tool used to carry out activities."""

    class Kind(models.TextChoices):
        THREE_D_PRINTER = "3d_printer", _("3D printer")
        LASER_CUTTER = "laser_cutter", _("Laser cutter")
        CNC_MACHINE = "cnc_machine", _("CNC machine")
        CUTTING_MACHINE = "cutting_machine", _("Cutting machine")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="equipment"
    )
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=32, choices=Kind, default=Kind.OTHER)
    technology = models.CharField(max_length=100, blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Equipment")
        verbose_name_plural = _("Equipment")
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "name"], name="unique_workshop_equipment_name"
            ),
        )

    def __str__(self) -> str:
        return self.name
