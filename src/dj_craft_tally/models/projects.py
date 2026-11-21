"""Core domain models for workshop inventory and projects."""

from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.identifiers import uuid7
from dj_craft_tally.models.core import Unit, Workshop
from dj_craft_tally.models.materials import Blueprint, Equipment, Material

QUANTITY_MAX_DIGITS = 15
QUANTITY_DECIMAL_PLACES = 6
MONEY_DECIMAL_PLACES = 2
MAX_SCALE_TO_BASE = Decimal("999999999.999999")


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


class ProjectSchedule(models.Model):
    """A calendar entry for work planned on a project."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        COMPLETE = "complete", _("Complete")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="schedule_entries"
    )
    starts_at = models.DateTimeField(help_text=_("When work is planned to begin."))
    ends_at = models.DateTimeField(
        null=True, blank=True, help_text=_("Optional planned end time.")
    )
    status = models.CharField(max_length=16, choices=Status, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Project schedule entry")
        verbose_name_plural = _("Project schedule entries")
        ordering = ("starts_at", "id")
        indexes = (models.Index(fields=["status", "starts_at"]),)

    def __str__(self) -> str:
        return f"{self.project}: {self.starts_at:%Y-%m-%d %H:%M}"

    def clean(self) -> None:
        super().clean()
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError(
                {"ends_at": _("The planned end must be after the planned start.")}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


class ProjectStockReservation(models.Model):
    """Material held for a scheduled project without changing the ledger."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    schedule_entry = models.ForeignKey(
        ProjectSchedule, on_delete=models.CASCADE, related_name="stock_reservations"
    )
    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="project_stock_reservations"
    )
    quantity = models.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("Quantity in the material's stock unit."),
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Project stock reservation")
        verbose_name_plural = _("Project stock reservations")
        ordering = ("schedule_entry__starts_at", "material__name")
        constraints = (
            models.UniqueConstraint(
                fields=["schedule_entry", "material"],
                name="unique_schedule_material_reservation",
            ),
        )

    def __str__(self) -> str:
        return f"{self.schedule_entry}: {self.material}"

    def clean(self) -> None:
        super().clean()
        if (
            self.schedule_entry_id
            and self.material_id
            and self.schedule_entry.project.workshop_id != self.material.workshop_id
        ):
            raise ValidationError(
                {"material": _("The material must belong to the project's workshop.")}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)


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
    cost = models.ForeignKey(
        "CurrencyTransaction",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="activities",
        help_text=_("The cost associated with this activity."),
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
        if (
            self.cost_id
            and self.workshop_id
            and self.cost.workshop_id != self.workshop_id
        ):
            errors["cost"] = _("The cost must belong to the activity's workshop.")
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
