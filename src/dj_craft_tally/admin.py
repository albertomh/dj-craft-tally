from decimal import Decimal
from typing import ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import ModelForm, Textarea
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.display import format_money, format_quantity
from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
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

_WIDE_TEXTAREA_MIN_WIDTH = 500


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("code", "name", "symbol", "symbol_position")
    search_fields: ClassVar = ("code", "name", "symbol")
    readonly_fields: ClassVar = (
        "code",
        "name",
        "symbol",
        "symbol_position",
    )

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


def _textarea_overrides(*, rows: int, min_width: int) -> dict:
    return {
        models.TextField: {
            "widget": Textarea(
                attrs={"rows": rows, "style": f"min-width: {min_width}px;"}
            )
        },
    }


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
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

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
    readonly_fields: ClassVar = (
        "symbol",
        "name",
        "dimension",
        "scale_to_base",
        "display_decimal_places",
    )

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "created_at")
    search_fields: ClassVar = ("name", "description")
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


@admin.register(WorkshopMembership)
class WorkshopMembershipAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("workshop", "user", "role", "created_at")
    list_filter: ClassVar = ("role",)
    search_fields: ClassVar = ("workshop__name", "user__username")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "kind", "workshop", "display_stock_balance")
    list_select_related: ClassVar = ("unit",)
    list_filter: ClassVar = ("workshop", "kind")
    search_fields: ClassVar = ("name",)
    ordering: ClassVar = (
        "kind",
        "name",
    )
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=5, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

    @admin.display(description=_("Stock balance"))
    def display_stock_balance(self, obj):
        return format_quantity(obj.stock_balance(), obj.unit, include_unit_code=True)


@admin.register(MaterialLot)
class MaterialLotAdmin(admin.ModelAdmin):
    fieldsets: ClassVar = (
        (
            None,
            {
                "fields": (
                    "material",
                    "reference",
                    "supplier",
                    "package_count",
                    "quantity_per_package",
                    "received_at",
                    ("purchase_currency", "purchase_amount"),
                    "notes",
                )
            },
        ),
    )
    list_display: ClassVar = (
        "received_at",
        "reference",
        "material",
        "supplier",
        "package_count",
        "display_quantity_per_package",
        "display_purchase_amount",
    )
    list_select_related: ClassVar = ("material__unit", "purchase_currency")
    list_filter: ClassVar = ("material", "purchase_currency")
    search_fields: ClassVar = ("reference", "supplier", "material__name")
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

    @admin.display(description=_("Quantity per package"), ordering="quantity_per_package")
    def display_quantity_per_package(self, obj):
        return format_quantity(
            obj.quantity_per_package, obj.material.unit, include_unit_code=True
        )

    @admin.display(description=_("Paid"), ordering="purchase_amount")
    def display_purchase_amount(self, obj):
        formatted = format_money(obj.purchase_amount, obj.purchase_currency)
        return format_html('<span class="ct-mono">{}</span>', formatted)

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

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        purchase_currency_field = form.base_fields["purchase_currency"]
        purchase_currency_field.widget.can_add_related = False
        purchase_currency_field.widget.can_view_related = False
        purchase_currency_field.help_text = ""
        form.base_fields["purchase_amount"].help_text = ""
        return form


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
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=5, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


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
    # ``sortable_by`` only applies to changelists, not tabular inlines. Keep
    # the immutable history useful on the project change view by showing the
    # newest transition first instead.
    ordering: ClassVar = ("-occurred_at", "-recorded_at")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    inlines: ClassVar = (ProjectStatusChangeInline,)
    list_display: ClassVar = ("name", "workshop", "blueprint", "status", "completed_at")
    list_filter: ClassVar = ("workshop", "status")
    search_fields: ClassVar = ("name", "description")
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

    class Media:
        css: ClassVar = {"all": ("dj_craft_tally/css/project_status_history.css",)}


@admin.register(ProjectStatusChange)
class ProjectStatusChangeAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "occurred_at",
        "project_link",
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

    @admin.display(description=_("Project"))
    def project_link(self, obj):
        project = obj.project
        if project:
            url = reverse("admin:crafttally_project_change", args=(project.pk,))
            return format_html(r'<a href="{}">{}</a>', url, project)
        return "-"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ProjectStepMeasurementInline(admin.TabularInline):
    model = ProjectStepMeasurement
    extra = 0
    formfield_overrides: ClassVar = _textarea_overrides(rows=1, min_width=200)


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
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

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
        "project_link",
        "project_step",
        "reference",
        "posted",
    )
    list_select_related: ClassVar = ("workshop", "project", "project_step")
    list_filter: ClassVar = ("workshop", "kind")

    @admin.display(description=_("Project"))
    def project_link(self, obj):
        project = obj.project
        if project:
            url = reverse("admin:crafttally_project_change", args=(project.pk,))
            return format_html(r'<a href="{}">{}</a>', url, project)
        return "-"

    @admin.action(description=_("Post selected draft transactions"))
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
        "material_link",
        "material_lot",
        "project_link",
        "display_quantity",
    )
    list_select_related: ClassVar = ("transaction", "material", "material_lot")
    list_filter: ClassVar = ("material", "transaction__project", "transaction__kind")
    ordering: ClassVar = (
        "-transaction__occurred_at",
        "-transaction__recorded_at",
        "id",
    )

    @admin.display(description=_("Material"))
    def material_link(self, obj):
        material = obj.material
        url = reverse("admin:crafttally_material_change", args=(material.pk,))
        return format_html(r'<a href="{}">{}</a>', url, material)

    @admin.display(description=_("Project"))
    def project_link(self, obj):
        project = obj.transaction.project
        if project:
            url = reverse("admin:crafttally_project_change", args=(project.pk,))
            return format_html(r'<a href="{}">{}</a>', url, project)
        return "-"

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
