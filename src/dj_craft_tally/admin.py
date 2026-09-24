from typing import ClassVar

from django.contrib import admin

from dj_craft_tally.models import (
    Equipment,
    Material,
    MaterialLot,
    Unit,
    Workshop,
    WorkshopMembership,
)


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
    list_display: ClassVar = ("name", "workshop", "unit")
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
