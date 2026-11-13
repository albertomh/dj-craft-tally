"""Tests for the custom admin dashboard on the CustomAdminSite."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.utils.translation import override

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    Project,
    Unit,
    Workshop,
)
from dj_craft_tally.sites import CustomAdminSite


@pytest.fixture
def dashboard_site():
    site = CustomAdminSite()
    site.register(Workshop)
    site.register(Material)
    site.register(Blueprint)
    site.register(Project)
    return site


@pytest.fixture
def dashboard_request(db):
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="admin", password="test"
    )
    return request


def render_dashboard(site, request):
    response = site.dashboard(request)
    response.render()
    return response.rendered_content


def test_dashboard_url_is_registered(dashboard_site):
    names = {
        name
        for pattern in dashboard_site.get_urls()
        for name in [getattr(pattern, "name", None)]
        if name
    }
    assert "crafttally_dashboard" in names
    # The default admin index must still be served.
    assert "index" in names


@pytest.mark.django_db
def test_dashboard_context_reports_summary_metrics(dashboard_site, dashboard_request):
    workshop = Workshop.objects.create(name="Studio")
    gram = Unit.objects.get(code="g")
    item = Unit.objects.get(code="item")
    material = Material.objects.create(workshop=workshop, name="Clay", unit=gram)
    blueprint = Blueprint.objects.create(
        workshop=workshop, name="Cup", output_name="Cup", output_unit=item
    )
    stock_quantity = Decimal("10")
    required_quantity = Decimal("2")
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=required_quantity
    )
    stock = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T00:00Z",
        reference="clay receipt",
    )
    InventoryTransactionLine.objects.create(
        transaction=stock, material=material, quantity=stock_quantity
    )
    stock.post()
    project = Project.objects.create(workshop=workshop, name="Kitchen tiles")
    project.set_status(Project.Status.ACTIVE)

    context = dashboard_site.dashboard_context(dashboard_request)

    assert context["workshop_count"] == 1
    assert context["material_count"] == 1
    assert context["blueprint_count"] == 1
    assert context["project_count"] == 1
    assert {
        "value": "active",
        "label": "Active",
        "count": 1,
        "color": "ct-status--active",
    } in context["projects_by_status"]
    (blueprint_entry,) = context["blueprints"]
    assert blueprint_entry["name"] == "Cup"
    assert blueprint_entry["runs"] == int(stock_quantity / required_quantity)
    assert blueprint_entry["pk"] == blueprint.pk
    assert context["recent_transactions"][0].reference == "clay receipt"


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
@override("en")
def test_dashboard_renders(dashboard_site, dashboard_request, workshop, item, gram):
    material = Material.objects.create(workshop=workshop, name="Clay", unit=gram)
    blueprint = Blueprint.objects.create(
        workshop=workshop, name="Cup", output_name="Cup", output_unit=item
    )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("2")
    )

    content = render_dashboard(dashboard_site, dashboard_request)

    assert "Workshop dashboard" in content
    assert "Available output" in content
    assert "Recent inventory activity" in content
    assert "No inventory movements recorded yet." in content
    assert "Cup" in content
    # Status cards are themed and link to the filtered project changelist.
    assert "ct-status--active" in content
    assert "?status=active" in content
    # The four summary cards link to their model changelists.
    assert "crafttally/blueprint/" in content
