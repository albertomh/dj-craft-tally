from collections import Counter
from typing import ClassVar

from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path

from dj_craft_tally.apps import DjCraftTallyConfig
from dj_craft_tally.display import format_quantity
from dj_craft_tally.models import (
    Blueprint,
    Equipment,
    InventoryTransaction,
    Material,
    Project,
    Workshop,
)


class CustomAdminSite(admin.AdminSite):
    MODEL_ORDER: ClassVar[list[str]] = [
        "Workshop",
        "WorkshopMembership",
        "Equipment",
        "Material",
        "MaterialLot",
        "Blueprint",
        "Project",
        "ProjectStep",
        "ProjectStatusChange",
        "InventoryTransaction",
        "InventoryTransactionLine",
    ]
    dashboard_template: ClassVar[str] = "admin/crafttally_index.html"
    STATUS_COLORS: ClassVar[dict[str, str]] = {
        "planned": "ct-status--planned",
        "active": "ct-status--active",
        "completed": "ct-status--completed",
        "stalled": "ct-status--stalled",
        "abandoned": "ct-status--abandoned",
        "on_hold": "ct-status--on-hold",
    }

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)

        order = {name: i for i, name in enumerate(self.MODEL_ORDER)}
        fallback = len(order)

        for app in app_list:
            if app["app_label"] == DjCraftTallyConfig.label:
                app["models"].sort(key=lambda m: order.get(m["object_name"], fallback))

        return app_list

    def dashboard_context(self, request) -> dict:
        """Return read-only summary metrics for the admin dashboard.

        Host projects can override or extend this method to add their own
        metrics; the default dashboard renders only the keys returned here.
        """
        status_counts = Counter(Project.objects.values_list("status", flat=True))
        projects_by_status = [
            {
                "value": status,
                "label": label,
                "count": status_counts.get(status, 0),
                "color": self.STATUS_COLORS.get(status),
            }
            for status, label in Project.Status.choices
        ]

        blueprints = [
            {
                "pk": blueprint.pk,
                "name": blueprint.name,
                "runs": blueprint.available_runs(),
                "output": format_quantity(
                    blueprint.available_output(),
                    blueprint.output_unit,
                    include_unit_code=True,
                ),
            }
            for blueprint in Blueprint.objects.select_related("output_unit").order_by(
                "name"
            )[:5]
        ]

        return {
            "workshop_count": Workshop.objects.count(),
            "material_count": Material.objects.count(),
            "equipment_count": Equipment.objects.count(),
            "blueprint_count": Blueprint.objects.count(),
            "project_count": Project.objects.count(),
            "projects_by_status": projects_by_status,
            "blueprints": blueprints,
            "recent_transactions": list(
                InventoryTransaction.objects.select_related(
                    "workshop", "project"
                ).order_by("-occurred_at", "-recorded_at")[:5]
            ),
            "materials_running_low": list(
                Material.objects.select_related("workshop", "unit").order_by("name")[:5]
            ),
        }

    def dashboard(self, request, extra_context=None):
        context = {
            **self.each_context(request),
            "title": "Workshop dashboard",
            "subtitle": None,
            "app_list": self.get_app_list(request),
            **self.dashboard_context(request),
            **(extra_context or {}),
        }
        for material in context.get("materials_running_low", []):
            material.stock_balance()
        context["materials_running_low"].sort(key=lambda m: m.stock_balance())
        request.current_app = self.name
        return TemplateResponse(request, self.dashboard_template, context)

    def get_urls(self):
        dashboard_url = path(
            "crafttally/",
            self.admin_view(self.dashboard),
            name="crafttally_dashboard",
        )
        return [dashboard_url, *super().get_urls()]
