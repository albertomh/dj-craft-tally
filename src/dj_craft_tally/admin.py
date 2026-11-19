from decimal import Decimal
from typing import ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import ModelForm, Textarea
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.display import format_money, format_quantity
from dj_craft_tally.models import (
    Activity,
    ActivityMaterial,
    ActivityMeasurement,
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
    CurrencyTransaction,
    Equipment,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Process,
    ProcessStep,
    Project,
    ProjectStatusChange,
    Unit,
    Workshop,
    WorkshopMembership,
)

_WIDE_TEXTAREA_MIN_WIDTH = 500


class DateTimeLayoutAdmin(admin.ModelAdmin):
    class Media:
        css: ClassVar = {"all": ("dj_craft_tally/css/datetime_layout.css",)}


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
    fieldsets: ClassVar = (
        (
            None,
            {
                "fields": (
                    "workshop",
                    "name",
                    "output_name",
                    "output_quantity",
                    "output_unit",
                    "description",
                )
            },
        ),
        (_("Cost estimate"), {"fields": ("display_cost_per_output_unit",)}),
    )
    readonly_fields: ClassVar = ("display_cost_per_output_unit",)
    list_display: ClassVar = (
        "name",
        "workshop",
        "output_name",
        "display_output_quantity",
        "display_cost_per_output_unit",
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

    @admin.display(description=_("Cost per output unit"))
    def display_cost_per_output_unit(self, obj: Blueprint):
        costs = obj.cost_per_output_unit().cost_per_unit
        if not costs:
            return "-"
        currencies = Currency.objects.in_bulk(costs)
        amounts = format_html_join(
            "<br>",
            "{}",
            (
                (format_money(amount, currencies.get(code)),)
                for code, amount in sorted(costs.items())
            ),
        )
        return format_html('<span class="ct-mono">{}</span>', amounts)


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


class MaterialLotInline(admin.TabularInline):
    model = MaterialLot
    extra = 0
    can_delete = False
    show_change_link = True
    fields: ClassVar = (
        "reference",
        "received_at",
        "supplier",
        "package_count",
        "quantity_per_package",
        "display_cost",
    )
    readonly_fields: ClassVar = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("transaction__currency")

    @admin.display(description=_("Paid"))
    def display_cost(self, obj):
        transaction = getattr(obj, "transaction", None)
        amount = -transaction.amount if transaction else None
        currency = transaction.currency if transaction else None
        return format_money(amount, currency)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    inlines: ClassVar = (MaterialLotInline,)
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
class MaterialLotAdmin(DateTimeLayoutAdmin):
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
    list_select_related: ClassVar = ("material__unit", "transaction__currency")
    list_filter: ClassVar = ("material",)
    search_fields: ClassVar = ("reference", "supplier", "material__name")
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

    @admin.display(description=_("Quantity per package"), ordering="quantity_per_package")
    def display_quantity_per_package(self, obj):
        return format_quantity(
            obj.quantity_per_package, obj.material.unit, include_unit_code=True
        )

    @admin.display(description=_("Paid"), ordering="transaction__amount")
    def display_purchase_amount(self, obj):
        transaction = getattr(obj, "transaction", None)
        if transaction:
            formatted = format_money(-transaction.amount, transaction.currency)
            return format_html('<span class="ct-mono">{}</span>', formatted)
        return "-"

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
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=5, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


class ProcessStepInline(admin.TabularInline):
    model = ProcessStep
    extra = 0


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    inlines: ClassVar = (ProcessStepInline,)
    list_display: ClassVar = ("name", "workshop")
    list_filter: ClassVar = ("workshop",)
    search_fields: ClassVar = ("name", "description")


@admin.register(ProcessStep)
class ProcessStepAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "process", "sequence")
    list_filter: ClassVar = ("process__workshop", "process")
    search_fields: ClassVar = ("name", "process__name")
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
class ProjectAdmin(DateTimeLayoutAdmin):
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


class ActivityMeasurementInline(admin.TabularInline):
    model = ActivityMeasurement
    extra = 0
    formfield_overrides: ClassVar = _textarea_overrides(rows=1, min_width=200)


class ActivityMaterialInline(admin.TabularInline):
    model = ActivityMaterial
    extra = 0


@admin.register(Activity)
class ActivityAdmin(DateTimeLayoutAdmin):
    fields: ClassVar = (
        "workshop",
        "project",
        "name",
        "process_step",
        "blueprint",
        "equipment",
        "reference",
        "cost",
        "outcome",
        "occurred_at",
        "notes",
    )
    inlines: ClassVar = (
        ActivityMaterialInline,
        ActivityMeasurementInline,
    )
    list_display: ClassVar = (
        "reference",
        "project",
        "name",
        "workshop",
        "equipment",
        "outcome",
        "occurred_at",
    )
    list_select_related: ClassVar = ("workshop", "project", "equipment")
    list_filter: ClassVar = ("workshop", "outcome", "equipment")
    formfield_overrides: ClassVar = _textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


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
class InventoryTransactionAdmin(DateTimeLayoutAdmin):
    actions: ClassVar = ("post_transactions",)
    inlines: ClassVar = (InventoryTransactionLineInline,)
    readonly_fields: ClassVar = ("posted",)
    date_hierarchy = "occurred_at"
    list_display: ClassVar = (
        "occurred_at",
        "workshop",
        "kind",
        "project_link",
        "activity",
        "reference",
        "posted",
    )
    list_select_related: ClassVar = ("workshop", "project", "activity")
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


@admin.register(CurrencyTransaction)
class CurrencyTransactionAdmin(DateTimeLayoutAdmin):
    formfield_overrides: ClassVar = {models.URLField: {"assume_scheme": "https"}}
    fields: ClassVar = (
        "workshop",
        "created_at",
        "description",
        ("currency", "amount"),
        "category",
        "payment_account",
        "merchant",
        "order_reference",
        "url",
        "notes",
        "project",
        "material_lot",
        "equipment",
    )
    list_display: ClassVar = (
        "created_at",
        "description",
        "workshop",
        "category",
        "merchant",
        "display_amount",
    )
    list_filter: ClassVar = ("workshop", "currency", "category", "created_at")
    search_fields: ClassVar = (
        "description",
        "category",
        "merchant",
        "order_reference",
        "notes",
    )
    autocomplete_fields: ClassVar = ("project", "material_lot", "equipment")

    @admin.display(description=_("Amount"))
    def display_amount(self, obj: CurrencyTransaction):
        formatted = format_money(obj.amount, obj.currency)
        if formatted is None:
            return "-"
        return format_html('<span class="ct-mono ct-right">{}</span>', formatted)
