"""Core domain models for workshop inventory and projects."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MONEY_DECIMAL_PLACES = 2
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class CurrencyTransaction(models.Model):
    """A signed financial transaction linked to workshop resources."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        "Workshop", on_delete=models.PROTECT, related_name="transactions"
    )
    created_at = models.DateTimeField(default=timezone.now)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        help_text=_("Negative for expenses, positive for income."),
    )
    currency = models.ForeignKey(
        "Currency", on_delete=models.PROTECT, related_name="transactions"
    )
    category = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Optional category or account path, such as workshop:tools."),
    )
    payment_account = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Optional payment account or other source of funds."),
    )
    merchant = models.CharField(max_length=255, blank=True)
    order_reference = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=1000, blank=True)
    notes = models.TextField(blank=True)
    project = models.ForeignKey(
        "Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transactions",
    )

    material_lot = models.OneToOneField(
        "MaterialLot",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transaction",
        help_text=_(
            "The whole transaction is the cost of this lot; income cannot be linked."
        ),
    )
    equipment = models.ForeignKey(
        "Equipment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transactions",
    )

    class Meta:
        ordering = ("-created_at", "description")

    def __str__(self):
        return self.description

    def clean(self):
        super().clean()
        errors = {}
        for field, resource in (
            ("project", self.project if self.project_id else None),
            ("equipment", self.equipment if self.equipment_id else None),
            ("material_lot", self.material_lot if self.material_lot_id else None),
        ):
            if resource and self.workshop_id:
                workshop_id = (
                    resource.material.workshop_id
                    if field == "material_lot"
                    else resource.workshop_id
                )
                if workshop_id != self.workshop_id:
                    errors[field] = _("This must belong to the same workshop.")
        if self.material_lot_id and self.amount is not None and self.amount > 0:
            errors["amount"] = _("A material lot purchase cannot be income.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
