from typing import ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError

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


class BlueprintMaterialRequirementInline(admin.TabularInline):
    model = BlueprintMaterialRequirement
    extra = 0


@admin.register(Blueprint)
class BlueprintAdmin(admin.ModelAdmin):
    inlines: ClassVar = (BlueprintMaterialRequirementInline,)
    list_display: ClassVar = (
        "name",
        "workshop",
        "output_quantity",
        "output_unit",
        "output_name",
        "available_runs",
        "available_output",
    )
    list_filter: ClassVar = ("workshop",)
    search_fields: ClassVar = ("name", "output_name")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("symbol", "name", "dimension", "scale_to_base")
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
    list_display: ClassVar = ("name", "workshop", "unit", "stock_balance")
    list_filter: ClassVar = ("workshop",)
    search_fields: ClassVar = ("name",)


@admin.register(MaterialLot)
class MaterialLotAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "reference",
        "material",
        "package_count",
        "quantity_per_package",
        "supplier",
    )
    list_filter: ClassVar = ("material",)
    search_fields: ClassVar = ("reference", "supplier", "material__name")


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
        "sequence",
        "name",
        "reference",
        "project",
        "equipment",
        "outcome",
        "occurred_at",
    )
    list_filter: ClassVar = ("outcome", "equipment")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        form_field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "sequence":
            form_field.widget.attrs["min"] = 1
        return form_field


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    actions: ClassVar = ("post_transactions",)
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

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(InventoryTransactionLine)
class InventoryTransactionLineAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("transaction", "material", "material_lot", "quantity")
    list_filter: ClassVar = ("material",)

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

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
