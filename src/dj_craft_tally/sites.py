from typing import ClassVar

from django.contrib import admin

from dj_craft_tally.apps import DjCraftTallyConfig


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

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)

        order = {name: i for i, name in enumerate(self.MODEL_ORDER)}
        fallback = len(order)

        for app in app_list:
            if app["app_label"] == DjCraftTallyConfig.label:
                app["models"].sort(key=lambda m: order.get(m["object_name"], fallback))

        return app_list
