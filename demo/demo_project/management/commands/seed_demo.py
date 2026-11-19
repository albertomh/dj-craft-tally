# ruff: noqa: S311, PLR0915, PLR0917

"""Create reproducible workshop examples for the local demo."""

import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dj_craft_tally.models import (
    Activity,
    ActivityMeasurement,
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
    Equipment,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Project,
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

        def jitter() -> datetime:
            # Random time 1-48h before now, so `now` stays the latest timestamp.
            hours_ago = random.randint(1, 48)
            minutes_ago = random.randint(0, 59)
            return now - timedelta(hours=hours_ago, minutes=minutes_ago)

        admin = user_model.objects.create_superuser("demo", password="demo")  # noqa: S106
        studio = Workshop.objects.create(
            name="Maker Studio", description="Sample 3D printing workshop"
        )
        WorkshopMembership.objects.create(workshop=studio, user=admin, role="owner")
        Workshop.objects.create(name="Woodworking Bench", description="Second workshop")
        gram = Unit.objects.get(code="g")
        item = Unit.objects.get(code="item")
        gbp = Currency.objects.get(code="GBP")

        def date_at_midnight(value):
            return timezone.make_aware(datetime.combine(value, datetime.min.time()))

        today = timezone.localdate()
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        quarter_start = today.replace(month=quarter_start_month, day=1)
        year_start = today.replace(month=1, day=1)
        last_week = today - timedelta(days=6)
        pla = Material.objects.create(
            workshop=studio, name="Blue PLA filament", unit=gram
        )
        bolts = Material.objects.create(workshop=studio, name="M3 bolts", unit=item)
        plywood = Material.objects.create(
            workshop=studio, name="Birch plywood sheets", unit=item
        )
        vinyl = Material.objects.create(
            workshop=studio, name="Adhesive vinyl sheets", unit=item
        )
        fabric = Material.objects.create(
            workshop=studio, name="Cotton canvas panels", unit=item
        )
        organisers = Material.objects.create(
            workshop=studio,
            name="Printed cable organisers",
            unit=item,
            kind=Material.Kind.OUTPUT,
        )
        coasters = Material.objects.create(
            workshop=studio,
            name="Laser-cut coasters",
            unit=item,
            kind=Material.Kind.OUTPUT,
        )
        stickers = Material.objects.create(
            workshop=studio, name="Sticker packs", unit=item, kind=Material.Kind.OUTPUT
        )
        totes = Material.objects.create(workshop=studio, name="Tote bags", unit=item)
        pegboards = Material.objects.create(
            workshop=studio, name="Pegboard panels", unit=item, kind=Material.Kind.OUTPUT
        )
        planters = Material.objects.create(
            workshop=studio, name="Printed planters", unit=item, kind=Material.Kind.OUTPUT
        )
        printer = Equipment.objects.create(
            workshop=studio, name="Workshop printer", kind="3d_printer", technology="FDM"
        )
        laser_cutter = Equipment.objects.create(
            workshop=studio, name="Laser cutter", kind="laser_cutter", technology="CO2"
        )
        vinyl_cutter = Equipment.objects.create(
            workshop=studio, name="Vinyl cutter", kind="vinyl_cutter", technology="blade"
        )
        drill_press = Equipment.objects.create(
            workshop=studio, name="Drill press", kind="drill_press", technology="manual"
        )
        sewing_machine = Equipment.objects.create(
            workshop=studio,
            name="Sewing machine",
            kind="sewing_machine",
            technology="mechanical",
        )
        pla_lot = MaterialLot.objects.create(
            material=pla,
            reference="PLA-BLUE-01",
            supplier="Example Filament Co.",
            package_count=2,
            quantity_per_package=Decimal("1000"),
            received_at=jitter(),
            purchase_amount=Decimal("48.00"),
            purchase_currency_id=gbp.code,
        )
        bolt_lot = MaterialLot.objects.create(
            material=bolts,
            reference="M3-01",
            supplier="Example Hardware",
            package_count=1,
            quantity_per_package=Decimal("100"),
            received_at=jitter(),
            purchase_amount=Decimal("18.50"),
            purchase_currency_id=gbp.code,
        )
        plywood_lot = MaterialLot.objects.create(
            material=plywood,
            reference="PLY-BIRCH-01",
            supplier="Example Timber",
            package_count=2,
            quantity_per_package=Decimal("10"),
            received_at=jitter(),
            purchase_amount=Decimal("72.00"),
            purchase_currency_id="GBP",
        )
        vinyl_lot = MaterialLot.objects.create(
            material=vinyl,
            reference="VINYL-01",
            supplier="Example Signs Supply",
            package_count=2,
            quantity_per_package=Decimal("10"),
            received_at=jitter(),
            purchase_amount=Decimal("24.00"),
            purchase_currency_id="GBP",
        )
        fabric_lot = MaterialLot.objects.create(
            material=fabric,
            reference="CANVAS-01",
            supplier="Example Textiles",
            package_count=1,
            quantity_per_package=Decimal("10"),
            received_at=jitter(),
            purchase_amount=Decimal("35.00"),
            purchase_currency_id="GBP",
        )

        MaterialLot.objects.create(
            material=pla,
            reference="PLA-BLUE-YEAR-START",
            supplier="Example Filament Co.",
            package_count=1,
            quantity_per_package=Decimal("1000"),
            received_at=date_at_midnight(year_start),
            purchase_amount=Decimal("22.00"),
            purchase_currency_id="GBP",
        )
        MaterialLot.objects.create(
            material=bolts,
            reference="M3-CURRENT-QUARTER",
            supplier="Example Hardware",
            package_count=1,
            quantity_per_package=Decimal("100"),
            received_at=date_at_midnight(quarter_start),
            purchase_amount=Decimal("19.00"),
            purchase_currency_id="GBP",
        )
        MaterialLot.objects.create(
            material=vinyl,
            reference="VINYL-LAST-WEEK",
            supplier="Example Signs Supply",
            package_count=1,
            quantity_per_package=Decimal("10"),
            received_at=date_at_midnight(last_week),
            purchase_amount=Decimal("17.50"),
            purchase_currency_id="GBP",
        )
        lots = {
            pla: pla_lot,
            bolts: bolt_lot,
            plywood: plywood_lot,
            vinyl: vinyl_lot,
            fabric: fabric_lot,
        }

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
            # The Desk trial batch is the latest transaction; the rest are jittered.
            if kind == "produce" and reference.startswith("Desk"):
                occurred_at = now
            else:
                occurred_at = jitter()

            entry = InventoryTransaction.objects.create(
                workshop=studio,
                kind=kind,
                occurred_at=occurred_at,
                reference=reference,
                project=project,
                activity=step,
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
            return entry

        def multi_line_movement(  # noqa: PLR0913
            kind, reference, lines, *, project=None, step=None, post=True
        ):
            # The Desk trial batch is the latest transaction; the rest are jittered.
            if kind == InventoryTransaction.Kind.PRODUCE and reference.startswith("Desk"):
                occurred_at = now
            else:
                occurred_at = jitter()

            entry = InventoryTransaction.objects.create(
                workshop=studio,
                kind=kind,
                occurred_at=occurred_at,
                reference=reference,
                project=project,
                activity=step,
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
            return entry

        multi_line_movement(
            InventoryTransaction.Kind.RECEIVE,
            "Shared supplies delivery",
            [
                (pla, None, "250", "Loose filament added to the shared bin."),
                (bolts, None, "20", "Spare fasteners added to the shared bin."),
            ],
            post=False,
        )

        # Blueprints
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

        recipes = {}

        def make_recipe(  # noqa: PLR0913
            key, name, description, output, output_quantity, equipment, step_name, inputs
        ):
            recipe_blueprint = Blueprint.objects.create(
                workshop=studio,
                name=name,
                output_name=output.name,
                output_quantity=output_quantity,
                output_unit=item,
                description=description,
            )
            for material, quantity in inputs:
                BlueprintMaterialRequirement.objects.create(
                    blueprint=recipe_blueprint,
                    material=material,
                    quantity=Decimal(quantity),
                )
            recipes[key] = {
                "blueprint": recipe_blueprint,
                "output": output,
                "output_quantity": str(output_quantity),
                "equipment": equipment,
                "step_name": step_name,
                "inputs": inputs,
            }

        make_recipe(
            "coasters",
            "Engraved coaster set",
            "Four engraved plywood coasters cut from one sheet.",
            coasters,
            4,
            laser_cutter,
            "Laser-cut coasters",
            [(plywood, "1")],
        )
        make_recipe(
            "stickers",
            "Die-cut sticker pack",
            "Ten die-cut vinyl stickers from two sheets.",
            stickers,
            10,
            vinyl_cutter,
            "Cut stickers",
            [(vinyl, "2")],
        )
        make_recipe(
            "pegboard",
            "Hanging tool board",
            "A drilled plywood panel for hanging tools.",
            pegboards,
            1,
            drill_press,
            "Drill hole grid",
            [(plywood, "1"), (bolts, "8")],
        )
        make_recipe(
            "tote",
            "Weekender tote",
            "A sewn tote bag from two canvas panels.",
            totes,
            1,
            sewing_machine,
            "Sew tote bag",
            [(fabric, "2")],
        )
        make_recipe(
            "planter",
            "Self-watering planter",
            "A printed plant pot with a drainage tray.",
            planters,
            1,
            printer,
            "Print planter",
            [(pla, "300")],
        )

        def new_project(name, description, key):
            return Project.objects.create(
                workshop=studio,
                name=name,
                blueprint=recipes[key]["blueprint"],
                description=description,
            )

        def complete_project(name, description, key, reference):
            recipe = recipes[key]
            done = new_project(name, description, key)
            done.set_status(Project.Status.ACTIVE, notes="Started")
            done_step = Activity.objects.create(
                project=done,
                name=recipe["step_name"],
                blueprint=recipe["blueprint"],
                equipment=recipe["equipment"],
                outcome="success",
                occurred_at=now,
            )
            main_material, main_quantity = recipe["inputs"][0]
            ActivityMeasurement.objects.create(
                activity=done_step,
                name=f"{main_material.name} used",
                quantity=Decimal(main_quantity),
                unit=main_material.unit,
            )
            output = recipe["output"]
            lines = [
                (material, lots[material], f"-{quantity}", f"{material.name} used.")
                for material, quantity in recipe["inputs"]
            ]
            lines.append(
                (output, None, recipe["output_quantity"], f"Finished {output.name}.")
            )
            multi_line_movement(
                InventoryTransaction.Kind.PRODUCE,
                reference,
                lines,
                project=done,
                step=done_step,
                post=False,
            )
            done.set_status(Project.Status.COMPLETE, notes="Finished and delivered")

        # Active project (1)
        project = Project.objects.create(
            workshop=studio,
            name="Desk organisers",
            blueprint=blueprint,
            description="Print a prototype for the workshop desk.",
        )
        project.set_status(Project.Status.ACTIVE, notes="Prototype underway")
        step = Activity.objects.create(
            project=project,
            name="Print prototype",
            blueprint=blueprint,
            equipment=printer,
            outcome="success",
            occurred_at=now,
        )
        ActivityMeasurement.objects.create(
            activity=step, name="Filament used", quantity=125, unit=gram
        )
        multi_line_movement(
            InventoryTransaction.Kind.PRODUCE,
            "Desk trial batch",
            [
                (pla, pla_lot, "-125", "Filament consumed by the print."),
                (bolts, bolt_lot, "-4", "Fasteners used in assembly."),
                (organisers, None, "1", "Completed cable organiser."),
            ],
            project=project,
            step=step,
            post=False,
        )

        # Planned projects (3): default status, no steps yet.
        new_project(
            "Open-day sticker run",
            "Sticker packs to hand out at the open day.",
            "stickers",
        )
        new_project(
            "Class tote bags",
            "Tote bags for the weekend sewing class.",
            "tote",
        )
        new_project(
            "Bench pegboard",
            "A pegboard for the second workshop's tool wall.",
            "pegboard",
        )

        # Completed projects (4).
        complete_project(
            "Market stall coasters",
            "Engraved coasters for the weekend market.",
            "coasters",
            "Saturday market restock",
        )
        complete_project(
            "Laptop sticker packs",
            "Sticker packs for the laptop-decoration workshop.",
            "stickers",
            "Monthly mail club",
        )
        complete_project(
            "Tool wall panel",
            "Drilled pegboard for the main tool wall.",
            "pegboard",
            "Replaces the wobbly old board",
        )
        complete_project(
            "Herb planters",
            "Printed planters for the windowsill herb garden.",
            "planter",
            "Greenery for the windowsill",
        )

        # Abandoned project (1)
        abandoned = new_project(
            "Canvas aprons",
            "Sewn aprons for the studio.",
            "tote",
        )
        abandoned.set_status(Project.Status.ACTIVE, notes="Started")
        abandoned.set_status(
            Project.Status.ABANDONED, notes="Dropped; pattern too fiddly for the stock"
        )

        if supports_posting:
            # Post everything first, then create the draft so it stays a draft.
            for tx in InventoryTransaction.objects.filter(workshop=studio, posted=False):
                tx.post()
            movement(
                pla,
                pla_lot,
                "-10",
                "adjust",
                "Stock check (not posted)",
                post=False,
            )
        self.stdout.write(
            self.style.SUCCESS("Created demo data. Sign in as demo / demo.")
        )
        self.stdout.write("Material quantities use the material's stock unit.")
