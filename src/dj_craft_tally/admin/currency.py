from typing import ClassVar

from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.admin._utils import DateTimeLayoutAdmin
from dj_craft_tally.display import format_money
from dj_craft_tally.models import Currency, CurrencyTransaction


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("code", "name", "symbol", "symbol_position")
    search_fields: ClassVar = ("code", "name", "symbol")
    readonly_fields: ClassVar = ("code", "name", "symbol", "symbol_position")

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


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
