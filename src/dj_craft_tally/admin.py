from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import ModelForm
from django.forms.widgets import Textarea
from django.utils import formats
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Equipment,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Project,
    ProjectStatusChange,
    ProjectStep,
    ProjectStepMeasurement,
    Unit,
    Workshop,
    WorkshopMembership,
)


def format_quantity(
    value: Decimal | None, unit: Unit, *, include_unit_code: bool = False
):
    """Render a quantity using the display precision of its unit."""
    if value is None:
        return None

    places = unit.display_decimal_places
    with localcontext() as context:
        context.prec = max(context.prec, len(value.as_tuple().digits) + places + 1)
        rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if not rounded:
        rounded = rounded.copy_abs()
    shown = formats.number_format(rounded, decimal_pos=places, use_l10n=True)
    if include_unit_code and unit.code != "item":
        shown = f"{shown} {unit.code}"
    return format_html(
        '<span title="{}">{}</span>',
        _("Exact: %(value)s") % {"value": value},
        shown,
    )


class BlueprintMaterialRequirementForm(ModelForm):
    class Meta:
        model = BlueprintMaterialRequirement
        fields = "__all__"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        instance = self.instance
        if (
            instance._state.adding
            or instance.quantity is None
            or not instance.material_id
        ):
            return

        unit = instance.material.unit
        value = Decimal(instance.quantity)

        # Never display fewer places than the stored value needs, otherwise
        # re-saving the form would silently truncate data.
        exponent = value.normalize().as_tuple().exponent
        if not isinstance(exponent, int):
            return
        needed = max(0, -exponent)
        places = max(unit.display_decimal_places, needed)

        # keep it a Decimal so has_changed() doesn't report a spurious change
        self.initial["quantity"] = Decimal(f"{value:.{places}f}")
        self.fields["quantity"].widget.attrs["step"] = (
            "1" if places == 0 else f"0.{'0' * (places - 1)}1"
        )


class BlueprintMaterialRequirementInline(admin.TabularInline):
    model = BlueprintMaterialRequirement
    form = BlueprintMaterialRequirementForm
    extra = 0
    formfield_overrides: ClassVar = {
        models.TextField: {
            "widget": Textarea(
                attrs={
                    "rows": 1,
                    "style": "height: 20px; min-width: 250px; resize: vertical;",
                }
            )
        },
    }


@admin.register(Blueprint)
class BlueprintAdmin(admin.ModelAdmin):
    inlines: ClassVar = (BlueprintMaterialRequirementInline,)
    list_display: ClassVar = (
        "name",
        "workshop",
        "output_name",
        "display_output_quantity",
        "available_runs",
        "display_available_output",
    )
    list_select_related: ClassVar = ("output_unit",)
    list_filter: ClassVar = ("workshop",)
    search_fields: ClassVar = ("name", "output_name")
    formfield_overrides: ClassVar = {
        models.TextField: {
            "widget": Textarea(attrs={"rows": 2, "style": "min-width: 500px;"})
        },
    }

    @admin.display(description=_("Output quantity"), ordering="output_quantity")
    def display_output_quantity(self, obj):
        return format_quantity(
            obj.output_quantity, obj.output_unit, include_unit_code=True
        )

    @admin.display(description=_("Available output"))
    def display_available_output(self, obj):
        return format_quantity(
            obj.available_output(), obj.output_unit, include_unit_code=True
        )


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "symbol",
        "name",
        "dimension",
        "scale_to_base",
        "display_decimal_places",
    )
    list_filter: ClassVar = ("dimension",)
    search_fields: ClassVar = ("code", "name", "symbol")


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "created_at")
    search_fields: ClassVar = ("name", "description")


@admin.register(WorkshopMembership)
class WorkshopMembershipAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("workshop", "user", "role", "created_at")
    list_filter: ClassVar = ("role",)
    search_fields: ClassVar = ("workshop__name", "user__username")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "workshop", "display_stock_balance")
    list_select_related: ClassVar = ("unit",)
    list_filter: ClassVar = ("workshop",)
    search_fields: ClassVar = ("name",)

    @admin.display(description=_("Stock balance"))
    def display_stock_balance(self, obj):
        return format_quantity(obj.stock_balance(), obj.unit, include_unit_code=True)


@admin.register(MaterialLot)
class MaterialLotAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "reference",
        "material",
        "package_count",
        "display_quantity_per_package",
        "supplier",
    )
    list_select_related: ClassVar = ("material__unit",)
    list_filter: ClassVar = ("material",)
    search_fields: ClassVar = ("reference", "supplier", "material__name")

    @admin.display(description=_("Quantity per package"), ordering="quantity_per_package")
    def display_quantity_per_package(self, obj):
        return format_quantity(
            obj.quantity_per_package, obj.material.unit, include_unit_code=True
        )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return (
                "material",
                "package_count",
                "quantity_per_package",
                "received_at",
                "reference",
            )
        return super().get_readonly_fields(request, obj)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "name",
        "workshop",
        "kind",
        "technology",
        "manufacturer",
        "model",
    )
    list_filter: ClassVar = ("workshop", "kind")
    search_fields: ClassVar = ("name", "technology", "manufacturer", "model")


class ProjectStatusChangeInline(admin.TabularInline):
    model = ProjectStatusChange
    can_delete = False
    extra = 0
    readonly_fields: ClassVar = (
        "previous_status",
        "status",
        "occurred_at",
        "recorded_at",
        "notes",
    )

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines: ClassVar = (ProjectStatusChangeInline,)
    list_display: ClassVar = ("name", "workshop", "blueprint", "status", "completed_at")
    list_filter: ClassVar = ("workshop", "status")
    search_fields: ClassVar = ("name", "description")


@admin.register(ProjectStatusChange)
class ProjectStatusChangeAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "occurred_at",
        "project",
        "previous_status",
        "status",
        "notes",
    )
    list_filter: ClassVar = ("status",)
    list_select_related: ClassVar = ("project",)
    ordering: ClassVar = ("-occurred_at",)
    readonly_fields: ClassVar = (
        "project",
        "previous_status",
        "status",
        "occurred_at",
        "recorded_at",
        "notes",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ProjectStepMeasurementInline(admin.TabularInline):
    model = ProjectStepMeasurement
    extra = 0


@admin.register(ProjectStep)
class ProjectStepAdmin(admin.ModelAdmin):
    inlines: ClassVar = (ProjectStepMeasurementInline,)
    list_display: ClassVar = (
        "project",
        "sequence",
        "name",
        "reference",
        "equipment",
        "outcome",
        "occurred_at",
    )
    list_select_related: ClassVar = ("project", "equipment")
    list_filter: ClassVar = ("outcome", "equipment")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        form_field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "sequence":
            form_field.widget.attrs["min"] = 1
        return form_field


class InventoryTransactionLineInline(admin.TabularInline):
    model = InventoryTransactionLine
    can_delete = False
    extra = 0
    fields: ClassVar = ("material", "material_lot", "display_quantity", "notes")
    readonly_fields: ClassVar = fields

    @admin.display(description=_("Quantity"))
    def display_quantity(self, obj):
        return format_quantity(obj.quantity, obj.material.unit, include_unit_code=True)

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    actions: ClassVar = ("post_transactions",)
    inlines: ClassVar = (InventoryTransactionLineInline,)
    readonly_fields: ClassVar = ("posted",)
    date_hierarchy = "occurred_at"
    list_display: ClassVar = (
        "occurred_at",
        "workshop",
        "kind",
        "project",
        "project_step",
        "reference",
        "posted",
    )
    list_select_related: ClassVar = ("workshop", "project", "project_step")
    list_filter: ClassVar = ("workshop", "kind")

    @admin.action(description="Post selected draft transactions")
    def post_transactions(self, request, queryset):
        for entry in queryset:
            try:
                entry.post()
            except ValidationError as exc:
                self.message_user(request, str(exc), level=messages.ERROR)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.posted:
            return tuple(field.name for field in self.model._meta.fields)
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        return (
            False if obj and obj.posted else super().has_delete_permission(request, obj)
        )

    def get_actions(self, request, action_location=None):
        if action_location is None:
            actions = super().get_actions(request)
        else:
            actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)
        return actions


@admin.register(InventoryTransactionLine)
class InventoryTransactionLineAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "transaction",
        "material",
        "material_lot",
        "display_quantity",
    )
    list_select_related: ClassVar = ("transaction", "material", "material_lot")
    list_filter: ClassVar = ("material",)
    ordering: ClassVar = (
        "-transaction__occurred_at",
        "-transaction__recorded_at",
        "id",
    )

    @admin.display(description=_("Quantity"), ordering="quantity")
    def display_quantity(self, obj):
        return format_quantity(obj.quantity, obj.material.unit, include_unit_code=True)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.transaction.posted:
            return tuple(field.name for field in self.model._meta.fields)
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        return (
            False
            if obj and obj.transaction.posted
            else super().has_delete_permission(request, obj)
        )

    def get_actions(self, request, action_location=None):
        if action_location is None:
            actions = super().get_actions(request)
        else:
            actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)
        return actions
