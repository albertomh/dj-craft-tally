"""Core domain models for workshop inventory and projects."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.display import format_quantity
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
    purchase_amount = models.DecimalField(
        null=True,
        blank=True,
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Amount paid for this delivery."),
    )
    purchase_currency = models.ForeignKey(
        "Currency",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchased_lots",
        help_text=_("Currency of the amount paid for this delivery."),
    )
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
        if self.purchase_amount is None and self.purchase_currency_id:
            errors["purchase_amount"] = _(
                "Enter the amount paid when selecting a purchase currency."
            )
        if self.purchase_amount is not None and not self.purchase_currency_id:
            errors["purchase_currency"] = _(
                "Select the currency of the amount paid for this delivery."
            )
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
            MaterialLot.objects.filter(
                purchase_amount__isnull=False,
                purchase_currency__isnull=False,
            )
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
                usages.append(
                    LotUsage(
                        lot=lot,
                        quantity=quantity,
                        currency=lot.purchase_currency_id,
                        cost=lot.purchase_amount * quantity / lot.total_quantity,
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


class ProjectQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if {"workshop", "workshop_id"} & kwargs.keys():
            raise ValidationError(
                _("Change a project's workshop through the model instance.")
            )
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if {"workshop", "workshop_id"} & set(fields):
            raise ValidationError(
                _("Change a project's workshop through the model instance.")
            )
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Project(models.Model):
    """A creative undertaking, optionally based on a reusable blueprint."""

    objects = ProjectQuerySet.as_manager()

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        ACTIVE = "active", _("Active")
        STALLED = "stalled", _("Stalled")
        COMPLETE = "complete", _("Complete")
        ABANDONED = "abandoned", _("Abandoned")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="projects"
    )
    name = models.CharField(max_length=200)
    blueprint = models.ForeignKey(
        Blueprint,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    status = models.CharField(max_length=16, choices=Status, default=Status.PLANNED)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")
        ordering = ("status", "name")

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.pk and not self._state.adding:
            original = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("workshop_id", flat=True)
                .first()
            )
            if (
                original is not None
                and original != self.workshop_id
                and self.activities.exists()
            ):
                raise ValidationError(
                    {"workshop": _("A project with activities cannot change workshop.")}
                )
        if self.blueprint_id and self.blueprint.workshop_id != self.workshop_id:
            raise ValidationError(
                {"blueprint": _("The blueprint must belong to the project's workshop.")}
            )

    def set_status(
        self, status: Status, *, occurred_at: datetime | None = None, notes: str = ""
    ) -> None:
        self._status_change_occurred_at = occurred_at
        self._status_change_notes = notes
        self.status = status
        try:
            self.save()
        finally:
            del self._status_change_occurred_at
            del self._status_change_notes

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        is_adding = self._state.adding
        previous_status = None
        if not is_adding and (
            kwargs.get("update_fields") is None or "status" in kwargs["update_fields"]
        ):
            previous_status = (
                type(self).objects.values_list("status", flat=True).get(pk=self.pk)
            )
        with transaction.atomic(using=self._state.db):
            super().save(*args, **kwargs)
            if is_adding:
                ProjectStatusChange.objects.create(
                    project=self, status=self.status, occurred_at=self.created_at
                )
            elif previous_status != self.status:
                ProjectStatusChange.objects.create(
                    project=self,
                    previous_status=previous_status,
                    status=self.status,
                    occurred_at=getattr(self, "_status_change_occurred_at", None)
                    or timezone.now(),
                    notes=getattr(self, "_status_change_notes", ""),
                )


class ProjectStatusChange(models.Model):
    """An immutable, timestamped entry in a project's status history."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="status_changes"
    )
    previous_status = models.CharField(max_length=16, choices=Project.Status, blank=True)
    status = models.CharField(max_length=16, choices=Project.Status)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Project status change")
        verbose_name_plural = _("Project status changes")
        db_table = "crafttally_project_status_change"
        ordering = ("occurred_at", "recorded_at")
        indexes = (models.Index(fields=["project", "occurred_at"]),)

    def __str__(self) -> str:
        transition = self.get_status_display()
        if self.previous_status:
            transition = f"{self.get_previous_status_display()} → {transition}"
        return f"{self.project}: {transition}"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError(_("Project status history entries cannot be changed."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        raise ValidationError(_("Project status history entries cannot be deleted."))


class Process(models.Model):
    """A reusable ordered recipe of operations for a workshop."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="processes"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = _("Processes")
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "name"], name="unique_workshop_process_name"
            ),
        )

    def __str__(self) -> str:
        return self.name


class ProcessStep(models.Model):
    """A named, ordered instruction within a reusable process."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    process = models.ForeignKey(Process, on_delete=models.CASCADE, related_name="steps")
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    name = models.CharField(max_length=100)
    instructions = models.TextField(blank=True)

    class Meta:
        ordering = ("process", "sequence")
        constraints = (
            models.UniqueConstraint(
                fields=["process", "sequence"], name="unique_process_step_sequence"
            ),
        )

    def __str__(self) -> str:
        return f"{self.process} · {self.sequence}: {self.name}"

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ActivityQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if {"workshop", "workshop_id", "project", "project_id"} & kwargs.keys():
            raise ValidationError(
                _("Change activity ownership through the model instance.")
            )
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if {"workshop", "workshop_id", "project", "project_id"} & set(fields):
            raise ValidationError(
                _("Change activity ownership through the model instance.")
            )
        return super().bulk_update(objs, fields, batch_size=batch_size)

    def bulk_create(self, objs, **kwargs):
        raise ValidationError(_("Create activities through the model instance."))


class Activity(models.Model):
    """A workshop activity, optionally associated with a project."""

    objects = ActivityQuerySet.as_manager()

    class Outcome(models.TextChoices):
        SUCCESS = "success", _("Success")
        FAILURE = "failure", _("Failure")
        PARTIAL_SUCCESS = "partial_success", _("Partial success")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="activities", blank=True
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="activities",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    process_step = models.ForeignKey(
        ProcessStep,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activities",
        help_text=_("The process step this activity follows."),
    )
    blueprint = models.ForeignKey(
        Blueprint,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activities",
    )
    equipment = models.ForeignKey(
        Equipment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activities",
    )
    reference = models.CharField(max_length=200, blank=True, unique=True)
    cost_amount = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    cost_currency = models.ForeignKey(
        "Currency",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activity_costs",
    )
    outcome = models.CharField(max_length=20, choices=Outcome, blank=True)
    occurred_at = models.DateTimeField(
        null=True, blank=True, help_text=_("Use when the time is known.")
    )
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Activity")
        verbose_name_plural = _("Activities")
        db_table = "crafttally_activity"
        ordering = ("-recorded_at", "id")

    def __str__(self) -> str:
        return f"{self.project or self.workshop}: {self.name}"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.project_id and not self.workshop_id:
            self.workshop = self.project.workshop
        if not self.workshop_id:
            errors["workshop"] = _("Select a workshop for this activity.")
        if self.project_id and self.workshop_id != self.project.workshop_id:
            errors["project"] = _("The project must belong to the activity's workshop.")
        if (
            self.workshop_id
            and self.process_step_id
            and self.process_step.process.workshop_id != self.workshop_id
        ):
            errors["process_step"] = _(
                "The process must belong to the activity's workshop."
            )
        if self.cost_amount is None and self.cost_currency_id:
            errors["cost_amount"] = _("Enter an amount when selecting a currency.")
        if self.cost_amount is not None and not self.cost_currency_id:
            errors["cost_currency"] = _("Select the currency of the cost.")
        if (
            self.workshop_id
            and self.blueprint_id
            and self.blueprint.workshop_id != self.workshop_id
        ):
            errors["blueprint"] = _(
                "The blueprint must belong to the activity's workshop."
            )
        if (
            self.workshop_id
            and self.equipment_id
            and self.equipment.workshop_id != self.workshop_id
        ):
            errors["equipment"] = _(
                "The equipment must belong to the activity's workshop."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = f"step-{self.id}"
        self.full_clean()
        super().save(*args, **kwargs)


class ActivityMeasurement(models.Model):
    """A named measurement recorded during or after an activity."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="measurements"
    )
    name = models.CharField(max_length=100)
    quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="activity_measurements"
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Activity measurement")
        verbose_name_plural = _("Activity measurements")
        db_table = "crafttally_activity_measurement"
        ordering = ("activity", "name")
        constraints = (
            models.UniqueConstraint(
                fields=["activity", "name"], name="unique_activity_measurement"
            ),
        )


class ActivityMaterial(models.Model):
    """An observed input or yield, independent of inventory ledger movements."""

    class Role(models.TextChoices):
        INPUT = "input", _("Input")
        OUTPUT = "output", _("Output")
        WASTE = "waste", _("Waste")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="materials"
    )
    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="step_observations"
    )
    role = models.CharField(max_length=16, choices=Role)
    quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.ForeignKey(
        Unit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="step_material_observations",
    )
    inventory_line = models.ForeignKey(
        "InventoryTransactionLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="material_observations",
        help_text=_("Optional posted inventory line for this material and activity."),
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Activity material")
        verbose_name_plural = _("Activity materials")
        ordering = ("role", "material__name")

    def __str__(self) -> str:
        return f"{self.activity}: {self.material} ({self.get_role_display()})"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if (
            self.activity_id
            and self.material_id
            and self.activity.workshop_id != self.material.workshop_id
        ):
            errors["material"] = _("The material must belong to the activity's workshop.")
        if self.quantity is None and self.unit_id:
            errors["quantity"] = _("Enter a quantity when selecting a unit.")
        if self.quantity is not None and not self.unit_id:
            errors["unit"] = _("Select the unit of the quantity.")
        if self.inventory_line_id:
            line = self.inventory_line
            if not line.transaction.posted:
                errors["inventory_line"] = _("Select a posted inventory line.")
            elif (
                line.material_id != self.material_id
                or line.transaction.activity_id != self.activity_id
            ):
                errors["inventory_line"] = _(
                    "The inventory line must match the material and activity."
                )
            elif (self.role == self.Role.OUTPUT and line.quantity < 0) or (
                self.role in (self.Role.INPUT, self.Role.WASTE) and line.quantity > 0
            ):
                errors["inventory_line"] = _(
                    "The inventory line direction must match the material role."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


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
        Project,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_transactions",
    )
    activity = models.ForeignKey(
        Activity,
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
        Material, on_delete=models.PROTECT, related_name="inventory_lines"
    )
    material_lot = models.ForeignKey(
        MaterialLot,
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
