from typing import ClassVar

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.admin._utils import DateTimeLayoutAdmin
from dj_craft_tally.display import format_quantity
from dj_craft_tally.models import InventoryTransaction, InventoryTransactionLine


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
            return tuple(
                "display_quantity" if field.name == "quantity" else field.name
                for field in self.model._meta.fields
            )
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
