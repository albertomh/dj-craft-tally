from typing import ClassVar

from django.contrib import admin

from dj_craft_tally.models import Unit


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("symbol", "name", "dimension", "scale_to_base")
    list_filter: ClassVar = ("dimension",)
    search_fields: ClassVar = ("code", "name", "symbol")
