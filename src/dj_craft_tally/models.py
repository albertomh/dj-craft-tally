"""Core domain models for workshop inventory and projects."""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


class Workshop(models.Model):
    """A shared workshop that owns inventory, equipment, and projects."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
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

    def update(self, **kwargs) -> int:
        if {"unit", "unit_id"}.intersection(kwargs):
            raise ValidationError(
                _("Material stock units must be changed through the model instance.")
            )
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None) -> int:
        if {"unit", "unit_id"}.intersection(fields):
            raise ValidationError(
                _("Material stock units cannot be changed with bulk_update().")
            )
        return super().bulk_update(objs, fields, batch_size=batch_size)


class Material(models.Model):
    """A consumable material, tracked in one stock unit."""

    objects = MaterialQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    workshop = models.ForeignKey(
        Workshop, on_delete=models.PROTECT, related_name="materials"
    )
    name = models.CharField(max_length=200)
    unit = models.ForeignKey("Unit", on_delete=models.PROTECT, related_name="materials")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
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

    def update(self, **kwargs):
        if {
            "material",
            "material_id",
            "package_count",
            "quantity_per_package",
            "received_at",
            "reference",
        }.intersection(kwargs):
            raise ValidationError(
                _("A lot's material and received quantity cannot be changed.")
            )
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, batch_size=None):
        if {
            "material",
            "material_id",
            "package_count",
            "quantity_per_package",
            "received_at",
            "reference",
        }.intersection(fields):
            raise ValidationError(
                _("A lot's material and received quantity cannot be changed.")
            )
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
        if self.package_count is not None and self.package_count < 1:
            raise ValidationError({"package_count": _("Enter at least one package.")})

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
    """A workshop machine or tool used to carry out project steps."""

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
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "name"], name="unique_workshop_equipment_name"
            ),
        )

    def __str__(self) -> str:
        return self.name


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
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "name"], name="unique_workshop_blueprint_name"
            ),
        )

    def __str__(self) -> str:
        return self.name

    def available_runs(self) -> int | None:
        """Return complete runs supported by stock, or None with no requirements."""
        requirements = self.requirements.select_related("material")
        capacities = [
            max(0, int(requirement.material.stock_balance() // requirement.quantity))
            for requirement in requirements
        ]
        return min(capacities) if capacities else None

    def available_output(self) -> Decimal | None:
        """Return output from complete available runs, or None if unspecified."""
        runs = self.available_runs()
        return None if runs is None else runs * self.output_quantity


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


class Project(models.Model):
    """A creative undertaking, optionally based on a reusable blueprint."""

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
        ordering = ("status", "name")

    def clean(self) -> None:
        super().clean()
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
        db_table = "crafttally_project_status_change"
        ordering = ("occurred_at", "recorded_at")
        indexes = (models.Index(fields=["project", "occurred_at"]),)

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError(_("Project status history entries cannot be changed."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:
        raise ValidationError(_("Project status history entries cannot be deleted."))


class ProjectStep(models.Model):
    """One ordered physical operation carried out as part of a project."""

    class Outcome(models.TextChoices):
        SUCCESS = "success", _("Success")
        FAILURE = "failure", _("Failure")
        PARTIAL_SUCCESS = "partial_success", _("Partial success")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="steps")
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    name = models.CharField(max_length=100)
    blueprint = models.ForeignKey(
        Blueprint,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_steps",
    )
    equipment = models.ForeignKey(
        Equipment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_steps",
    )
    reference = models.CharField(max_length=200, blank=True, unique=True)
    source_reference = models.CharField(max_length=500, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome, blank=True)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "crafttally_project_step"
        ordering = ("project", "sequence")
        constraints = (
            models.UniqueConstraint(
                fields=["project", "sequence"], name="unique_project_step_sequence"
            ),
        )

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.blueprint_id and self.blueprint.workshop_id != self.project.workshop_id:
            errors["blueprint"] = _(
                "The blueprint must belong to the project's workshop."
            )
        if self.equipment_id and self.equipment.workshop_id != self.project.workshop_id:
            errors["equipment"] = _(
                "The equipment must belong to the project's workshop."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = f"step-{self.id}"
        self.full_clean()
        super().save(*args, **kwargs)


class ProjectStepMeasurement(models.Model):
    """A named measurement recorded during or after a project step."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project_step = models.ForeignKey(
        ProjectStep, on_delete=models.CASCADE, related_name="measurements"
    )
    name = models.CharField(max_length=100)
    quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal("0"))],
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="project_step_measurements"
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "crafttally_project_step_measurement"
        ordering = ("project_step__sequence", "name")
        constraints = (
            models.UniqueConstraint(
                fields=["project_step", "name"], name="unique_project_step_measurement"
            ),
        )


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
    project_step = models.ForeignKey(
        ProjectStep,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inventory_transactions",
    )
    reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "crafttally_inventory_tx"
        ordering = ("-occurred_at", "-recorded_at")
        indexes = (
            models.Index(fields=["occurred_at"], name="crafttally_occurred_at_idx"),
            models.Index(fields=["kind"]),
        )

    def clean(self) -> None:
        super().clean()
        errors = {}
        if self.project_id and self.project.workshop_id != self.workshop_id:
            errors["project"] = _(
                "The project must belong to the transaction's workshop."
            )
        if self.project_step_id:
            if self.project_step.project.workshop_id != self.workshop_id:
                errors["project_step"] = _(
                    "The project step must belong to the transaction's workshop."
                )
            if self.project_id and self.project_step.project_id != self.project_id:
                errors["project_step"] = _(
                    "The project step must belong to the selected project."
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
