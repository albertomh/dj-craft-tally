from decimal import Decimal
from typing import ClassVar

from django.contrib import admin
from django.db import models
from django.forms import ModelForm, Textarea
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.admin._utils import (
    _WIDE_TEXTAREA_MIN_WIDTH,
    DateTimeLayoutAdmin,
    textarea_overrides,
)
from dj_craft_tally.display import format_money, format_quantity
from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
    Material,
    MaterialLot,
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
        exponent = value.normalize().as_tuple().exponent
        if not isinstance(exponent, int):
            return
        needed = max(0, -exponent)
        places = max(unit.display_decimal_places, needed)
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
    formfield_overrides: ClassVar = textarea_overrides(
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
    ordering: ClassVar = ("kind", "name")
    formfield_overrides: ClassVar = textarea_overrides(
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
    formfield_overrides: ClassVar = textarea_overrides(
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
