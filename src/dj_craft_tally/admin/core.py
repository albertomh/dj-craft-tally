from typing import ClassVar

from django.contrib import admin

from dj_craft_tally.admin._utils import _WIDE_TEXTAREA_MIN_WIDTH, textarea_overrides
from dj_craft_tally.models import Unit, Workshop, WorkshopMembership


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "symbol",
        "name",
        "dimension",
        "base_unit",
        "scale_to_base",
        "display_decimal_places",
    )
    list_filter: ClassVar = ("dimension",)
    search_fields: ClassVar = ("code", "name", "symbol")
    readonly_fields: ClassVar = (
        "symbol",
        "name",
        "dimension",
        "base_unit",
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
    formfield_overrides: ClassVar = textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


@admin.register(WorkshopMembership)
class WorkshopMembershipAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("workshop", "user", "role", "created_at")
    list_filter: ClassVar = ("role",)
    search_fields: ClassVar = ("workshop__name", "user__username")
