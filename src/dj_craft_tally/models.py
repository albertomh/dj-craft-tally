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
        related_name="craft_tally_workshop_memberships",
    )
    role = models.CharField(max_length=16, choices=Role, default=Role.MEMBER)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("workshop", "user")
        constraints = (
            models.UniqueConstraint(
                fields=["workshop", "user"], name="unique_workshop_membership"
            ),
        )

    def __str__(self) -> str:
        return f"{self.user} in {self.workshop}"


class Material(models.Model):
    """A consumable material, tracked in one stock unit."""

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


class MaterialLot(models.Model):
    """A received batch of one material, including package details."""

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
        ordering = ("material__name", "reference")
        constraints = (
            models.UniqueConstraint(
                fields=["material", "reference"], name="unique_material_lot_reference"
            ),
        )

    @property
    def total_quantity(self) -> Decimal:
        return self.package_count * self.quantity_per_package

    def save(self, *args, **kwargs) -> None:
        if not self.reference:
            self.reference = f"lot-{self.id}"
        super().save(*args, **kwargs)

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
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    notes = models.TextField(blank=True)

    class Meta:
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
