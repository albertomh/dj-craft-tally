"""Core domain models for workshop inventory and projects."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.display import format_quantity
from dj_craft_tally.identifiers import uuid7
from dj_craft_tally.models.core import Workshop

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MONEY_DECIMAL_PLACES = 2
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class MaterialQuerySet(models.QuerySet):
    """QuerySet safeguards for material stock units."""

    PROTECTED_FIELDS = frozenset({"unit", "unit_id"})

    def _check_fields_mutable(self, fields: Iterable[str]) -> None:
        if self.PROTECTED_FIELDS.intersection(fields):
            raise ValidationError(
                _("Material stock units must be changed through the model instance.")
            )

    def update(self, **kwargs) -> int:
        self._check_fields_mutable(kwargs)
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None) -> int:
        self._check_fields_mutable(fields)
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Material(models.Model):
    """A consumable material, tracked in one stock unit."""

    objects = MaterialQuerySet.as_manager()

    class Kind(models.TextChoices):
        INPUT = "input", _("Input")
        OUTPUT = "output", _("Output")
        INTERMEDIATE = "intermediate", _("Intermediate")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="materials"
    )
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=32, choices=Kind, default=Kind.INPUT)
    unit = models.ForeignKey("Unit", on_delete=models.PROTECT, related_name="materials")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("Material")
        verbose_name_plural = _("Materials")
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "name"], name="unique_workshop_material_name"
            ),
        )

    def __str__(self) -> str:
        return self.name

    def stock_balance(self) -> Decimal:
        """Return the sum of signed inventory movements in the stock unit."""
        return sum(
            self.inventory_lines.filter(transaction__posted=True)
            .values_list("quantity", flat=True)
            .iterator(),
            Decimal(0),
        )

    @cached_property
    def display_stock_balance(self) -> str:
        """Return a formatted quantity string with unit code."""
        return format_quantity(self.stock_balance(), self.unit, include_unit_code=True)

    def save(self, *args, **kwargs) -> None:
        unit_is_being_saved = kwargs.get("update_fields") is None or bool(
            {"unit", "unit_id"}.intersection(kwargs["update_fields"])
        )
        if not self._state.adding and unit_is_being_saved:
            previous_unit_id = (
                type(self).objects.values_list("unit_id", flat=True).get(pk=self.pk)
            )
            has_quantity_references = (
                self.lots.exists()
                or self.blueprint_requirements.exists()
                or self.inventory_lines.exists()
            )
            if previous_unit_id != self.unit_id and has_quantity_references:
                raise ValidationError(
                    {
                        "unit": _(
                            "The stock unit cannot change after this material has been "
                            "used in inventory, lots, or blueprints."
                        )
                    }
                )
        super().save(*args, **kwargs)


class MaterialLotQuerySet(models.QuerySet):
    """Prevent changes that would disconnect a lot from its receipt."""

    PROTECTED_FIELDS = frozenset(
        {
            "material",
            "material_id",
            "package_count",
            "quantity_per_package",
            "received_at",
            "reference",
        }
    )

    def _check_fields_mutable(self, fields: Iterable[str]) -> None:
        if self.PROTECTED_FIELDS.intersection(fields):
            raise ValidationError(
                _("A lot's material and received quantity cannot be changed.")
            )

    def update(self, **kwargs):
        self._check_fields_mutable(kwargs)
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        self._check_fields_mutable(fields)
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(_("Create lots individually to record their receipts."))


class MaterialLot(models.Model):
    """A received batch of one material, including package details."""

    objects = MaterialLotQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="lots")
    reference = models.CharField(max_length=200, blank=True)
    supplier = models.CharField(max_length=200, blank=True)
    package_count = models.PositiveIntegerField(default=1)
    quantity_per_package = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Material lot")
        verbose_name_plural = _("Material lots")
        db_table = "crafttally_material_lot"
        ordering = ("material__name", "reference")
        constraints = (
            models.UniqueConstraint(
                fields=["material", "reference"], name="unique_material_lot_reference"
            ),
        )

    @property
    def total_quantity(self) -> Decimal:
        return self.package_count * self.quantity_per_package

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.package_count is not None and self.package_count < 1:
            errors["package_count"] = _("Enter at least one package.")
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = f"lot-{self.id}"
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            is_new = self._state.adding
            if not is_new:
                previous = (
                    type(self).objects.using(using).select_for_update().get(pk=self.pk)
                )
                if (
                    self.material_id,
                    self.package_count,
                    self.quantity_per_package,
                    self.received_at,
                    self.reference,
                ) != (
                    previous.material_id,
                    previous.package_count,
                    previous.quantity_per_package,
                    previous.received_at,
                    previous.reference,
                ):
                    raise ValidationError(
                        _("A lot's material and received quantity cannot be changed.")
                    )
            self.full_clean()
            super().save(*args, **kwargs)
            if is_new:
                from .inventory import (  # noqa: PLC0415
                    InventoryTransaction,
                    InventoryTransactionLine,
                )

                receipt = InventoryTransaction.objects.using(using).create(
                    workshop=self.material.workshop,
                    kind=InventoryTransaction.Kind.RECEIVE,
                    occurred_at=self.received_at or timezone.now(),
                    reference=self.reference,
                )
                InventoryTransactionLine.objects.using(using).create(
                    transaction=receipt,
                    material=self.material,
                    material_lot=self,
                    quantity=self.total_quantity,
                )
                receipt.post()

    def __str__(self) -> str:
        return f"{self.material}: {self.reference}"


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


@dataclass(frozen=True, slots=True)
class LotUsage:
    lot: "MaterialLot"
    quantity: Decimal
    currency: str
    cost: Decimal  # cost of the quantity used, for the whole batch


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    cost_per_unit: dict[str, Decimal]
    usages: tuple[LotUsage, ...]


class Blueprint(models.Model):
    """A reusable plan for making a named output from material requirements."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="blueprints"
    )
    name = models.CharField(max_length=200)
    output_name = models.CharField(max_length=200)
    output_quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        default=Decimal("1"),
        validators=[MinValueValidator(0)],
    )
    output_unit = models.ForeignKey(
        "Unit", on_delete=models.PROTECT, related_name="blueprint_outputs"
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = _("Blueprint")
        verbose_name_plural = _("Blueprints")
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "name"], name="unique_workshop_blueprint_name"
            ),
        )

    def __str__(self) -> str:
        return self.name

    def available_runs(self) -> int | None:
        requirements = self.requirements.select_related("material")
        capacities = [
            max(0, int(requirement.material.stock_balance() // requirement.quantity))
            for requirement in requirements
        ]
        return min(capacities) if capacities else None

    def available_output(self) -> Decimal | None:
        runs = self.available_runs()
        return None if runs is None else runs * self.output_quantity

    def cost_per_output_unit(self) -> CostBreakdown:
        """The estimated material cost per output unit, plus the lots used.

        Requirements are costed from the oldest priced lots first, using newer
        lots when needed. Lots without a receipt date follow dated lots;
        ties are ordered by ID. Available quantities are the sums of posted
        lot movements. A nonzero balance of posted movements without a lot
        makes the estimate unavailable. Costs are grouped by currency; an empty
        ``cost_per_unit`` means a requirement cannot be costed.
        """
        if self.output_quantity <= 0:
            return CostBreakdown({}, ())

        priced_lots = (
            MaterialLot.objects.filter(models.Q(transaction__amount__lte=0))
            .select_related("transaction")
            .annotate(
                remaining_stock=models.Sum(
                    "inventory_lines__quantity",
                    filter=models.Q(inventory_lines__transaction__posted=True),
                )
            )
            .order_by(models.F("received_at").asc(nulls_last=True), "pk")
        )

        requirements = self.requirements.select_related("material").prefetch_related(
            models.Prefetch("material__lots", queryset=priced_lots, to_attr="priced_lots")
        )

        usages: list[LotUsage] = []
        for requirement in requirements:
            unallocated = requirement.material.inventory_lines.filter(
                transaction__posted=True, material_lot__isnull=True
            ).aggregate(total=models.Sum("quantity"))["total"]
            if unallocated:
                return CostBreakdown({}, ())
            remaining = requirement.quantity
            for lot in requirement.material.priced_lots:
                if remaining <= 0:
                    break
                available = max(lot.remaining_stock or Decimal("0"), Decimal("0"))
                if not available:
                    continue
                quantity = min(remaining, available)
                transaction = lot.transaction
                currency = transaction.currency_id
                amount = -transaction.amount
                usages.append(
                    LotUsage(
                        lot=lot,
                        quantity=quantity,
                        currency=currency,
                        cost=amount * quantity / lot.total_quantity,
                    )
                )
                remaining -= quantity
            if remaining > 0:
                return CostBreakdown({}, ())

        totals: dict[str, Decimal] = {}
        for usage in usages:
            totals[usage.currency] = totals.get(usage.currency, Decimal("0")) + usage.cost

        return CostBreakdown(
            cost_per_unit={c: t / self.output_quantity for c, t in totals.items()},
            usages=tuple(usages),
        )

    def last_made(self) -> datetime | None:
        from .inventory import InventoryTransaction  # noqa: PLC0415

        return InventoryTransaction.objects.filter(
            project__blueprint=self,
            kind=InventoryTransaction.Kind.PRODUCE,
            posted=True,
        ).aggregate(last=models.Max("occurred_at"))["last"]


class BlueprintMaterialRequirement(models.Model):
    """The quantity of a material needed for one run of a blueprint."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    blueprint = models.ForeignKey(
        Blueprint, on_delete=models.CASCADE, related_name="requirements"
    )
    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="blueprint_requirements"
    )
    quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        help_text=_("Quantity in the material's stock unit."),
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Blueprint material requirement")
        verbose_name_plural = _("Blueprint material requirements")
        db_table = "crafttally_blueprint_material_req"
        ordering = ("blueprint__name", "material__name")
        constraints = (
            models.UniqueConstraint(
                fields=["blueprint", "material"],
                name="unique_blueprint_material_requirement",
            ),
        )

    def clean(self) -> None:
        super().clean()
        if (
            self.blueprint_id
            and self.material_id
            and self.blueprint.workshop_id != self.material.workshop_id
        ):
            raise ValidationError(
                {"material": _("The material must belong to the blueprint's workshop.")}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
