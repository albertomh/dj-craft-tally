from typing import ClassVar

from django.contrib import admin

from dj_craft_tally.admin._utils import (
    _WIDE_TEXTAREA_MIN_WIDTH,
    DateTimeLayoutAdmin,
    textarea_overrides,
)
from dj_craft_tally.models import CurrencyTransaction, Equipment, EquipmentMaterial


class EquipmentTransactionInline(admin.TabularInline):
    model = CurrencyTransaction
    fields: ClassVar = (
        "created_at",
        "description",
        "amount",
        "currency",
        "workshop",
        "merchant",
    )
    extra = 0
    show_change_link = True

    class Media:
        css: ClassVar = {"all": ("dj_craft_tally/css/datetime_layout.css",)}


class EquipmentMaterialInline(admin.TabularInline):
    model = EquipmentMaterial
    extra = 0
    fields: ClassVar = (
        "material",
        "role",
        "reserve_quantity",
    )
    autocomplete_fields: ClassVar = ("material",)


@admin.register(Equipment)
class EquipmentAdmin(DateTimeLayoutAdmin):
    inlines: ClassVar = (EquipmentMaterialInline, EquipmentTransactionInline)
    list_display: ClassVar = (
        "name",
        "workshop",
        "kind",
        "technology",
        "manufacturer",
        "model",
    )
    list_filter: ClassVar = ("workshop", "kind")
    search_fields: ClassVar = (
        "name",
        "manufacturer",
        "technology",
        "model",
    )
    formfield_overrides: ClassVar = textarea_overrides(
        rows=5, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )
