"""Core domain models for workshop inventory and projects."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7
from dj_craft_tally.models.core import Workshop

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MONEY_DECIMAL_PLACES = 2
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class LedgerQuerySet(models.QuerySet):
    """Disallow bulk mutations, which bypass ledger validation."""

    def update(self, **kwargs):
        raise ValidationError(_("Bulk updates of inventory records are not supported."))

    def delete(self):
        raise ValidationError(_("Bulk deletion of inventory records is not supported."))

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(_("Bulk updates of inventory records are not supported."))

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(_("Bulk creation of inventory records is not supported."))


class InventoryTransaction(models.Model):
    """A draft inventory movement that becomes immutable when posted."""

    objects = LedgerQuerySet.as_manager()

    class Kind(models.TextChoices):
        RECEIVE = "receive", _("Received")
        PRODUCE = "produce", _("Produced")
        CONSUME = "consume", _("Consumed")
        ADJUST = "adjust", _("Adjusted")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="inventory_transactions"
    )
    kind = models.CharField(max_length=16, choices=Kind)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    posted = models.BooleanField(default=False, editable=False)
    project = models.ForeignKey(
        "Project",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_transactions",
    )
    activity = models.ForeignKey(
        "Activity",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_transactions",
    )
    reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Inventory transaction")
        verbose_name_plural = _("Inventory transactions")
        db_table = "crafttally_inventory_tx"
        ordering = ("-occurred_at", "-recorded_at")
        indexes = (
            models.Index(fields=["occurred_at"], name="crafttally_occurred_at_idx"),
            models.Index(fields=["kind"]),
        )

    def __str__(self) -> str:
        identifier = self.reference or self.occurred_at.strftime("%Y-%m-%d %H:%M")
        return f"{self.get_kind_display()} | {identifier}"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.project_id and self.project.workshop_id != self.workshop_id:
            errors["project"] = _(
                "The project must belong to the transaction's workshop."
            )
        if self.activity_id:
            if self.activity.workshop_id != self.workshop_id:
                errors["activity"] = _(
                    "The activity must belong to the transaction's workshop."
                )
            if self.project_id and self.activity.project_id != self.project_id:
                errors["activity"] = _(
                    "The activity must belong to the selected project."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            if not self._state.adding:
                current = (
                    type(self).objects.using(using).select_for_update().get(pk=self.pk)
                )
                if current.posted:
                    raise ValidationError(
                        _("Posted inventory transactions cannot be changed.")
                    )
            if self.posted:
                raise ValidationError(_("Use post() to post an inventory transaction."))
            self.full_clean()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            current = type(self).objects.using(using).select_for_update().get(pk=self.pk)
            if current.posted:
                raise ValidationError(
                    _("Posted inventory transactions cannot be deleted.")
                )
            return super().delete(*args, **kwargs)

    def post(self) -> None:
        """Post a saved draft with at least one line; correct it with a new entry."""
        using = self._state.db
        with transaction.atomic(using=using):
            current = type(self).objects.using(using).select_for_update().get(pk=self.pk)
            if current.posted:
                raise ValidationError(_("This inventory transaction is already posted."))
            if not current.lines.exists():
                raise ValidationError(
                    _("An inventory transaction needs at least one line.")
                )
            models.QuerySet.update(
                type(self).objects.using(using).filter(pk=self.pk), posted=True
            )
            self.posted = True


class InventoryTransactionLine(models.Model):
    """A signed material movement within an inventory transaction."""

    objects = LedgerQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    transaction = models.ForeignKey(
        InventoryTransaction, on_delete=models.CASCADE, related_name="lines"
    )
    material = models.ForeignKey(
        "Material", on_delete=models.PROTECT, related_name="inventory_lines"
    )
    material_lot = models.ForeignKey(
        "MaterialLot",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_lines",
    )
    quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        help_text=_("Quantity in the material's stock unit."),
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Inventory transaction line")
        verbose_name_plural = _("Inventory transaction lines")
        db_table = "crafttally_inventory_tx_line"
        ordering = ("transaction__occurred_at", "id")
        constraints = (
            models.CheckConstraint(
                condition=~models.Q(quantity=0),
                name="inventory_transaction_line_quantity_nonzero",
            ),
        )

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.transaction_id and self.transaction.posted:
            errors["transaction"] = _("Lines cannot be added to a posted transaction.")
        if self.material_lot_id and self.material_lot.material_id != self.material_id:
            errors["material_lot"] = _("The lot must belong to the selected material.")
        if (
            self.transaction_id
            and self.material_id
            and self.transaction.workshop_id != self.material.workshop_id
        ):
            errors["material"] = _(
                "The material must belong to the transaction's workshop."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            if not self._state.adding:
                previous = type(self).objects.using(using).get(pk=self.pk)
                if previous.transaction_id != self.transaction_id:
                    raise ValidationError(
                        _("An inventory line cannot be moved to another transaction.")
                    )
            parent = (
                InventoryTransaction.objects.using(using)
                .select_for_update()
                .get(pk=self.transaction_id)
            )
            if parent.posted or (
                not self._state.adding
                and type(self)
                .objects.using(using)
                .filter(pk=self.pk, transaction__posted=True)
                .exists()
            ):
                raise ValidationError(
                    _("Lines of posted inventory transactions cannot be changed.")
                )
            self.full_clean()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            current = type(self).objects.using(using).get(pk=self.pk)
            parent = (
                InventoryTransaction.objects.using(using)
                .select_for_update()
                .get(pk=current.transaction_id)
            )
            if parent.posted:
                raise ValidationError(
                    _("Lines of posted inventory transactions cannot be deleted.")
                )
            return super().delete(*args, **kwargs)
