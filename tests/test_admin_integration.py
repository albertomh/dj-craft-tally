from decimal import Decimal
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.utils.translation import override

import dj_craft_tally.admin as ct_admin
from dj_craft_tally.models import (
    Activity,
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
    CurrencyTransaction,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Project,
)
from tests.conftest import create_priced_lot


@pytest.mark.django_db
def test_material_admin_displays_stock_using_unit_precision(workshop, item, gram):
    material_admin: ct_admin.MaterialAdmin = admin.site._registry[Material]
    assert "display_stock_balance" in material_admin.list_display
    assert "brand" in material_admin.list_display
    assert "kind" in material_admin.list_display
    assert "brand" in material_admin.search_fields
    assert "kind" in material_admin.list_filter
    for unit, quantity, shown in (
        (item, "96", "96"),
        (gram, "125.5", "125.50 g"),
        (gram, "0.004", "0.00 g"),
        (gram, "-0.005", "-0.01 g"),
    ):
        material = Material.objects.create(
            workshop=workshop, name=f"Stock {quantity}", unit=unit
        )
        movement = InventoryTransaction.objects.create(
            workshop=workshop, kind="adjust", occurred_at="2026-01-01T00:00Z"
        )
        InventoryTransactionLine.objects.create(
            transaction=movement, material=material, quantity=Decimal(quantity)
        )
        movement.post()
        with override("en"):
            rendered = str(material_admin.display_stock_balance(material))
        assert f">{shown}</span>" in rendered
        assert str(material.stock_balance()) in rendered
        assert material.stock_balance() == Decimal(quantity)


def test_project_status_change_admin_renders_missing_project_as_dash():
    status_change_admin = admin.site._registry[ct_admin.ProjectStatusChange]

    assert status_change_admin.project_link(SimpleNamespace(project=None)) == "-"


@pytest.mark.django_db
def test_material_lot_admin_displays_purchase_amount(material: Material):
    lot = create_priced_lot(
        material=material,
        quantity_per_package=1,
        purchase_amount=Decimal("1.25"),
        purchase_currency=Currency.objects.get(code="GBP"),
    )
    lot_admin = admin.site._registry[MaterialLot]

    assert (
        str(lot_admin.display_purchase_amount(lot))
        == '<span class="ct-mono">£1.25</span>'
    )
    assert ct_admin.format_money(None, Currency.objects.get(code="GBP")) is None


@pytest.mark.django_db
def test_blueprint_admin_displays_cost_per_output_unit(blueprint, material):
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("2")
    )
    create_priced_lot(
        material=material,
        quantity_per_package=2,
        purchase_amount=Decimal("12.50"),
        purchase_currency=Currency.objects.get(code="GBP"),
    )

    blueprint_admin: ct_admin.BlueprintAdmin = admin.site._registry[Blueprint]

    assert "display_cost_per_output_unit" in blueprint_admin.list_display
    assert (
        str(blueprint_admin.display_cost_per_output_unit(blueprint))
        == '<span class="ct-mono">£12.50</span>'
    )


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_activity_admin_groups_currency_and_amount(client, workshop):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    activity = Activity.objects.create(workshop=workshop, name="Print")
    client.force_login(user)

    for url in (
        "/admin/crafttally/activity/add/",
        f"/admin/crafttally/activity/{activity.pk}/change/",
    ):
        response = client.get(url)
        assert response.status_code == HTTPStatus.OK
        rows = [
            [field.field.name for field in line]
            for fieldset in response.context["adminform"]
            for line in fieldset
        ]
        assert ["cost"] in rows
        assert b'id="id_cost"' in response.content


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_datetime_inputs_use_the_shared_admin_layout(client):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    client.force_login(user)

    for model, field in (
        ("activity", "occurred_at"),
        ("inventorytransaction", "occurred_at"),
        ("materiallot", "received_at"),
        ("project", "completed_at"),
    ):
        response = client.get(f"/admin/crafttally/{model}/add/")
        assert response.status_code == HTTPStatus.OK
        assert b"dj_craft_tally/css/datetime_layout.css" in response.content
        assert f'id="id_{field}_0"'.encode() in response.content
        assert f'id="id_{field}_1"'.encode() in response.content


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_expense_admin_groups_currency_and_amount(client, workshop):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    transaction = CurrencyTransaction.objects.create(
        workshop=workshop,
        created_at="2026-11-01T00:00Z",
        description="Resin",
        amount=Decimal("12.50"),
        currency_id="GBP",
    )
    client.force_login(user)

    for url in (
        "/admin/crafttally/currencytransaction/add/",
        f"/admin/crafttally/currencytransaction/{transaction.pk}/change/",
    ):
        response = client.get(url)
        assert response.status_code == HTTPStatus.OK
        rows = [
            [field.field.name for field in line]
            for fieldset in response.context["adminform"]
            for line in fieldset
        ]
        assert ["currency", "amount"] in rows
        assert response.context["adminform"].form.fields["url"].clean("example.com") == (
            "https://example.com"
        )
        assert b'id="id_currency"' in response.content
        assert b'id="id_amount"' in response.content


@pytest.mark.django_db
def test_format_money_normalizes_negative_zero_and_supports_suffix_currency():
    euro = Currency.objects.get(code="EUR")
    usd = Currency.objects.get(code="USD")

    assert str(ct_admin.format_money(Decimal("-0.001"), euro)) == "0.00 €"
    assert str(ct_admin.format_money(Decimal("-12.50"), euro)) == "-12.50 €"
    assert str(ct_admin.format_money(Decimal("-12.50"), usd)) == "-$12.50"


@pytest.mark.django_db
def test_display_amount(rf):
    usd = Currency.objects.get(code="USD")
    model_admin = ct_admin.CurrencyTransactionAdmin(CurrencyTransaction, AdminSite())

    valid_tx = CurrencyTransaction(amount=Decimal("-12.50"), currency=usd)
    assert str(model_admin.display_amount(valid_tx)) == (
        '<span class="ct-mono ct-right">-$12.50</span>'
    )

    missing_amount_tx = CurrencyTransaction(amount=None, currency=usd)
    assert model_admin.display_amount(missing_amount_tx) == "-"


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_project_status_history_inline_hides_detached_row_heading(client, workshop):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    project = Project.objects.create(workshop=workshop, name="Desk organisers")
    client.force_login(user)

    response = client.get(f"/admin/crafttally/project/{project.pk}/change/")

    assert response.status_code == HTTPStatus.OK
    assert b"dj_craft_tally/css/project_status_history.css" in response.content


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_material_admin_page_shows_unit_precision(client, workshop, item):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    material = Material.objects.create(workshop=workshop, name="Bolts", unit=item)
    movement = InventoryTransaction.objects.create(
        workshop=workshop, kind="adjust", occurred_at="2026-01-01T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=movement, material=material, quantity=96
    )
    movement.post()
    client.force_login(user)
    response = client.get("/admin/crafttally/material/")
    assert response.status_code == HTTPStatus.OK
    assert b">96</span>" in response.content
    assert b"Exact: 96.000000" in response.content
    assert b"column-unit" not in response.content


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_currency_breadcrumb_uses_title_cased_app_name(client):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    client.force_login(user)

    response = client.get("/admin/crafttally/currency/")

    assert response.status_code == HTTPStatus.OK
    assert b'<a href="/admin/crafttally/">Craft Tally</a>' in response.content


@pytest.mark.django_db
def test_inventory_transaction_line_admin_orders_by_parent_occurrence(workshop, material):
    earlier = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T00:00Z",
    )
    later = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-02T00:00Z",
    )
    earlier_line = InventoryTransactionLine.objects.create(
        transaction=earlier, material=material, quantity=1
    )
    later_line = InventoryTransactionLine.objects.create(
        transaction=later, material=material, quantity=1
    )
    request = RequestFactory().get("/")
    request.user = get_user_model()(is_staff=True, is_superuser=True)

    lines = admin.site._registry[InventoryTransactionLine].get_queryset(request)

    assert list(lines.filter(pk__in=(earlier_line.pk, later_line.pk))) == [
        later_line,
        earlier_line,
    ]


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_admin_changelists_use_human_labels_and_unit_precision(
    client, workshop, item, gram
):
    assert ct_admin.format_quantity(None, item) is None
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    blueprint = Blueprint.objects.create(
        workshop=workshop,
        name="Clay batch",
        output_name="Clay",
        output_quantity=6,
        output_unit=gram,
    )
    material = Material.objects.create(workshop=workshop, name="Clay", unit=gram)
    bolts = Material.objects.create(workshop=workshop, name="M3 bolts", unit=item)
    filament = Material.objects.create(
        workshop=workshop, name="Blue PLA filament", unit=gram
    )
    create_priced_lot(
        material=filament, reference="PLA-BLUE-01", quantity_per_package=2000
    )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=2
    )
    stock = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T00:00Z",
    )
    InventoryTransactionLine.objects.create(
        transaction=stock, material=material, quantity=4
    )
    stock.post()
    project = Project.objects.create(workshop=workshop, name="Kitchen tiles")
    project.set_status(Project.Status.ACTIVE)
    step = Activity.objects.create(
        project=project,
        name="Press tiles",
        occurred_at="2026-01-02T00:00Z",
    )
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2026-01-02T12:30Z",
        project=project,
        activity=step,
        reference="Clay for first batch",
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=bolts, quantity=-2
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=filament, quantity=-125
    )
    client.force_login(user)

    blueprint_response = client.get("/admin/crafttally/blueprint/")
    assert blueprint_response.status_code == HTTPStatus.OK
    assert b">6.00 g</span>" in blueprint_response.content
    assert b">12.00 g</span>" in blueprint_response.content
    assert b"column-output_unit" not in blueprint_response.content

    material_response = client.get("/admin/crafttally/material/")
    assert material_response.status_code == HTTPStatus.OK
    assert b">4.00 g</span>" in material_response.content
    assert b"column-unit" not in material_response.content

    lot_response = client.get("/admin/crafttally/materiallot/")
    assert lot_response.status_code == HTTPStatus.OK
    assert b">2000.00 g</span>" in lot_response.content

    step_response = client.get("/admin/crafttally/activity/")
    assert step_response.status_code == HTTPStatus.OK
    assert b"Kitchen tiles" in step_response.content
    assert b"Project object" not in step_response.content

    change_response = client.get("/admin/crafttally/projectstatuschange/")
    assert change_response.status_code == HTTPStatus.OK
    assert b"Kitchen tiles" in change_response.content
    assert b"Planned" in change_response.content
    assert b"Active" in change_response.content
    assert b"ProjectStatusChange object" not in change_response.content

    transaction_response = client.get("/admin/crafttally/inventorytransaction/")
    assert transaction_response.status_code == HTTPStatus.OK
    assert b"Kitchen tiles" in transaction_response.content
    assert b"Kitchen tiles: Press tiles" in transaction_response.content

    line_response = client.get("/admin/crafttally/inventorytransactionline/")
    assert line_response.status_code == HTTPStatus.OK
    assert str(transaction).encode() in line_response.content
    assert b">-2</span>" in line_response.content
    assert b">-2.000000</span>" not in line_response.content
    assert b">-125.00 g</span>" in line_response.content


@pytest.mark.django_db
def test_material_change_page_shows_its_lots(client, django_user_model, material):
    user = django_user_model.objects.create_superuser(
        username="lots-admin", password="pw"
    )
    client.force_login(user)
    lot = create_priced_lot(
        material=material,
        reference="VISIBLE-LOT",
        quantity_per_package=10,
        purchase_amount=Decimal("12.50"),
        purchase_currency_id="GBP",
    )
    with override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"]):
        response = client.get(f"/admin/crafttally/material/{material.pk}/change/")
    assert response.status_code == HTTPStatus.OK
    assert b"VISIBLE-LOT" in response.content
    assert str(lot.pk).encode() in response.content
    assert b"12.50" in response.content
