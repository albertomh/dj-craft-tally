"""Tests for the custom admin dashboard on the CustomAdminSite."""

import html
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.utils.translation import override

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
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
    stock_quantity = Decimal("8")
    required_quantity = Decimal("2")
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=required_quantity
    )
    lot = MaterialLot.objects.create(
        material=material,
        quantity_per_package=required_quantity,
        purchase_amount=Decimal("12.50"),
        purchase_currency=Currency.objects.get(code="GBP"),
    )
    stock = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T00:00Z",
        reference="clay receipt",
    )
    InventoryTransactionLine.objects.create(
        transaction=stock, material=material, material_lot=lot, quantity=stock_quantity
    )
    stock.post()
    project = Project.objects.create(workshop=workshop, name="Kitchen tiles")
    project.set_status(Project.Status.ACTIVE)

    context = dashboard_site.dashboard_context(dashboard_request)

    assert context["workshop_count"] == 1
    assert context["material_count"] == Material.objects.count()
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
    assert blueprint_entry["runs"] == int(
        (stock_quantity + required_quantity) / required_quantity
    )
    assert "12.50" in str(blueprint_entry["cost"][0]["amount"])
    assert blueprint_entry["pk"] == blueprint.pk
    assert "clay receipt" in {
        transaction.reference for transaction in context["recent_transactions"]
    }


@pytest.mark.django_db
def test_dashboard_context_formats_expenditure_periods(
    dashboard_site, dashboard_request, material
):
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=1,
        received_at="2026-04-01T00:00Z",
        purchase_amount=Decimal("12.50"),
        purchase_currency=Currency.objects.get(code="GBP"),
    )

    context = dashboard_site.dashboard_context(dashboard_request)

    assert context["has_expenditure"]
    ytd = next(
        period
        for period in context["expenditure_periods"]
        if period["label"] == "Year to date"
    )
    assert ytd["entries"][0]["code"] == "GBP"
    assert "12.50" in str(ytd["entries"][0]["amount"])


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

    assert "Craft Tally" in content
    assert "Available output" in content
    assert "Inventory activity" in content
    assert "No inventory movements recorded yet." in content
    assert "Cup" in content
    # Status cards are themed and link to the filtered project changelist.
    assert "ct-status--active" in content
    assert "?status=active" in content
    # The four summary cards link to their model changelists.
    assert "crafttally/blueprint/" in content


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
@override("en")
def test_dashboard_expenditure_cards_show_each_total_and_empty_period(
    dashboard_site, dashboard_request, monkeypatch
):
    monkeypatch.setattr(
        "dj_craft_tally.sites.expenditure_periods",
        lambda: [
            {"label": "Last week", "totals": {}},
            {"label": "Current quarter", "totals": {"GBP": Decimal("12.50")}},
            {
                "label": "Year to date",
                "totals": {"GBP": Decimal("15.00"), "EUR": Decimal("8.00")},
            },
        ],
    )
    content = render_dashboard(dashboard_site, dashboard_request)
    cards = content.split('<div class="ct-card ct-expenditure-card">')[1:]
    last_week, quarter, year = cards
    assert '<span class="ct-count">—</span>' in html.unescape(last_week)
    assert "£12.50" in quarter
    assert "£15.00" in year
    assert "8.00" in year
    assert "currencies" not in "".join(cards)


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
@override("en")
def test_dashboard_expenditure_cards_show_dashes_when_no_purchases(
    dashboard_site, dashboard_request
):
    content = render_dashboard(dashboard_site, dashboard_request)
    cards = content.split('<div class="ct-card ct-expenditure-card">')[1:]
    last_week, quarter, year = cards
    assert all(
        '<span class="ct-count">—</span>' in html.unescape(card)
        for card in (last_week, quarter, year)
    )
    assert "No purchases recorded yet." not in content
