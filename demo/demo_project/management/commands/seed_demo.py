"""Create reproducible workshop examples for the local demo."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Equipment,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Project,
    ProjectStep,
    ProjectStepMeasurement,
    Unit,
    Workshop,
    WorkshopMembership,
)


class Command(BaseCommand):
    help = "Create local demo data and the demo/demo admin account."

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        has_user = user_model.objects.filter(username="demo").exists()
        has_workshop = Workshop.objects.filter(name="Maker Studio").exists()
        if has_user and has_workshop:
            self.stdout.write("Demo data already exists; nothing changed.")
            return
        if has_user or has_workshop:
            message = "Demo username or workshop already exists. Use a fresh database."
            raise CommandError(message)

        supports_posting = hasattr(InventoryTransaction, "post")
        now = timezone.now()
        admin = user_model.objects.create_superuser("demo", password="demo")  # noqa: S106
        studio = Workshop.objects.create(
            name="Maker Studio", description="Sample 3D printing workshop"
        )
        WorkshopMembership.objects.create(workshop=studio, user=admin, role="owner")
        Workshop.objects.create(name="Woodworking Bench", description="Second workshop")
        gram = Unit.objects.get(code="g")
        item = Unit.objects.get(code="item")
        pla = Material.objects.create(
            workshop=studio, name="Blue PLA filament", unit=gram
        )
        bolts = Material.objects.create(workshop=studio, name="M3 bolts", unit=item)
        organisers = Material.objects.create(
            workshop=studio, name="Printed cable organisers", unit=item
        )
        printer = Equipment.objects.create(
            workshop=studio, name="Workshop printer", kind="3d_printer", technology="FDM"
        )
        pla_lot = MaterialLot.objects.create(
            material=pla,
            reference="PLA-BLUE-01",
            supplier="Example Filament Co.",
            package_count=2,
            quantity_per_package=Decimal("1000"),
            received_at=now,
        )
        bolt_lot = MaterialLot.objects.create(
            material=bolts,
            reference="M3-01",
            supplier="Example Hardware",
            package_count=1,
            quantity_per_package=Decimal("100"),
            received_at=now,
        )

        def movement(  # noqa: PLR0913
            material,
            lot,
            quantity,
            kind,
            reference,
            *,
            project=None,
            step=None,
            post=True,
        ):
            entry = InventoryTransaction.objects.create(
                workshop=studio,
                kind=kind,
                occurred_at=now,
                reference=reference,
                project=project,
                project_step=step,
            )
            values = {
                "transaction": entry,
                "material": material,
                "material_lot": lot,
                "quantity": Decimal(quantity),
            }
            InventoryTransactionLine.objects.create(**values)
            if supports_posting and post:
                entry.post()

        def multi_line_movement(  # noqa: PLR0913
            kind, reference, lines, *, project=None, step=None, post=True
        ):
            entry = InventoryTransaction.objects.create(
                workshop=studio,
                kind=kind,
                occurred_at=now,
                reference=reference,
                project=project,
                project_step=step,
            )
            for material, lot, quantity, notes in lines:
                InventoryTransactionLine.objects.create(
                    transaction=entry,
                    material=material,
                    material_lot=lot,
                    quantity=Decimal(quantity),
                    notes=notes,
                )
            if supports_posting and post:
                entry.post()

        if not pla_lot.inventory_lines.exists():
            movement(pla, pla_lot, "2000", "receive", "PLA receipt")
            movement(bolts, bolt_lot, "100", "receive", "Bolt receipt")
        multi_line_movement(
            InventoryTransaction.Kind.RECEIVE,
            "Shared supplies delivery",
            [
                (pla, None, "250", "Loose filament added to the shared bin."),
                (bolts, None, "20", "Spare fasteners added to the shared bin."),
            ],
        )

        blueprint = Blueprint.objects.create(
            workshop=studio,
            name="Cable organiser",
            output_name="Cable organiser",
            output_quantity=1,
            output_unit=item,
            description="A printed organiser with four fasteners.",
        )
        requirement = {
            "blueprint": blueprint,
            "material": pla,
            "quantity": Decimal("120"),
        }
        BlueprintMaterialRequirement.objects.create(**requirement)
        BlueprintMaterialRequirement.objects.create(
            blueprint=blueprint, material=bolts, quantity=4
        )
        project = Project.objects.create(
            workshop=studio,
            name="Desk organisers",
            blueprint=blueprint,
            description="Print a prototype for the workshop desk.",
        )
        project.set_status(Project.Status.ACTIVE, notes="Prototype underway")
        step = ProjectStep.objects.create(
            project=project,
            sequence=1,
            name="Print prototype",
            blueprint=blueprint,
            equipment=printer,
            outcome="success",
            occurred_at=now,
        )
        ProjectStepMeasurement.objects.create(
            project_step=step, name="Filament used", quantity=125, unit=gram
        )
        multi_line_movement(
            InventoryTransaction.Kind.PRODUCE,
            "Prototype production run",
            [
                (pla, pla_lot, "-125", "Filament consumed by the print."),
                (bolts, bolt_lot, "-4", "Fasteners used in assembly."),
                (organisers, None, "1", "Completed cable organiser."),
            ],
            project=project,
            step=step,
        )
        if supports_posting:
            movement(
                pla,
                pla_lot,
                "-10",
                "adjust",
                "Draft stock check (not posted)",
                post=False,
            )
        self.stdout.write(
            self.style.SUCCESS("Created demo data. Sign in as demo / demo.")
        )
        self.stdout.write("Material quantities use the material's stock unit.")
