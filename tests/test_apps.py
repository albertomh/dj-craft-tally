from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings

from dj_craft_tally.admin_apps import CustomAdminConfig
from dj_craft_tally.models import InventoryTransactionLine, Material, Unit
from dj_craft_tally.sites import CustomAdminSite


def test_unit_is_registered_in_django_admin():
    assert admin.site.is_registered(Unit)


@override_settings(ROOT_URLCONF="tests.admin_urls")
def test_custom_admin_site_orders_registered_models(db):
    assert CustomAdminConfig.default_site == "dj_craft_tally.sites.CustomAdminSite"
    site = CustomAdminSite()
    site.register(InventoryTransactionLine)
    site.register(Material)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="admin", password="test"
    )

    app_list = site.get_app_list(request)

    craft_tally_app = next(app for app in app_list if app["app_label"] == "crafttally")
    assert [model["object_name"] for model in craft_tally_app["models"]] == [
        "Material",
        "InventoryTransactionLine",
    ]
