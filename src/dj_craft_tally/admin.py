from typing import ClassVar

from django.contrib import admin

from dj_craft_tally.models import Unit, Workshop, WorkshopMembership


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
