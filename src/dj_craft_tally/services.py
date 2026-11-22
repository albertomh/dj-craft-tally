"""Reusable domain services for inventory and workshop reporting."""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict

from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.models import (
    CurrencyTransaction,
    InventoryTransactionLine,
    ProjectStockReservation,
)

if TYPE_CHECKING:
    from dj_craft_tally.models import EquipmentMaterial


class ConsumableForecastError(ValueError):
    """Raised when a consumable forecast receives invalid parameters."""


INVALID_MONTHS_MESSAGE = "months must be at least 1."
NAIVE_AS_OF_MESSAGE = "as_of must be timezone-aware."


class TotalForPeriod(TypedDict):
    key: str
    label: str
    totals: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class ConsumableForecast:
    """A consumption-based replenishment forecast for one equipment material."""

    equipment_material: "EquipmentMaterial"
    period_start: datetime
    as_of: datetime
    consumed_quantity: Decimal
    average_daily_consumption: Decimal
    stock_quantity: Decimal
    scheduled_reservation_quantity: Decimal
    available_quantity: Decimal
    reserve_quantity: Decimal
    depletion_at: datetime | None


def _subtract_calendar_months(value: datetime, months: int) -> datetime:
    """Return ``value`` shifted back by whole calendar months."""
    month_number = value.month - months
    year = value.year + (month_number - 1) // 12
    month = (month_number - 1) % 12 + 1
    return value.replace(
        year=year,
        month=month,
        day=min(value.day, calendar.monthrange(year, month)[1]),
    )


def consumable_forecast(
    equipment_material: "EquipmentMaterial",
    *,
    months: int = 3,
    as_of: datetime | None = None,
) -> ConsumableForecast:
    """Forecast when an equipment material reaches its configured reserve.

    Consumption is calculated from negative, posted ``consume`` ledger lines
    linked to activities performed with the associated equipment. ``months``
    is a calendar-month lookback window.
    """
    if months < 1:
        raise ConsumableForecastError(INVALID_MONTHS_MESSAGE)

    as_of = as_of or timezone.now()
    if timezone.is_naive(as_of):
        raise ConsumableForecastError(NAIVE_AS_OF_MESSAGE)
    period_start = _subtract_calendar_months(as_of, months)
    consumed_quantity = -(
        InventoryTransactionLine.objects.filter(
            transaction__posted=True,
            transaction__kind="consume",
            transaction__activity__equipment=equipment_material.equipment,
            material=equipment_material.material,
            quantity__lt=0,
            transaction__occurred_at__gte=period_start,
            transaction__occurred_at__lt=as_of,
        ).aggregate(total=Sum("quantity"))["total"]
        or Decimal("0")
    )
    period_days = Decimal(str((as_of - period_start).total_seconds() / 86400))
    average_daily_consumption = consumed_quantity / period_days
    stock_quantity = equipment_material.material.stock_balance()
    scheduled_reservation_quantity = ProjectStockReservation.objects.filter(
        material=equipment_material.material,
        schedule_entry__status="scheduled",
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    available_quantity = stock_quantity - scheduled_reservation_quantity

    if average_daily_consumption == 0:
        depletion_at = None
    else:
        depletion_days = available_quantity / average_daily_consumption
        depletion_at = as_of + timedelta(days=float(max(depletion_days, Decimal("0"))))

    return ConsumableForecast(
        equipment_material=equipment_material,
        period_start=period_start,
        as_of=as_of,
        consumed_quantity=consumed_quantity,
        average_daily_consumption=average_daily_consumption,
        stock_quantity=stock_quantity,
        scheduled_reservation_quantity=scheduled_reservation_quantity,
        available_quantity=available_quantity,
        reserve_quantity=equipment_material.reserve_quantity,
        depletion_at=depletion_at,
    )


def expenditure_periods(*, as_of: date | None = None) -> list[TotalForPeriod]:
    """Return transaction totals by period.

    The result contains raw :class:`~decimal.Decimal` amounts grouped by
    currency code. It deliberately contains no admin or presentation-layer
    values, so other backends and frontends can format the data themselves.
    ``as_of`` is available for deterministic reports and tests; by default the
    current UTC date is used.
    """
    today = as_of or datetime.now(UTC).date()
    last_week_start = today - timedelta(days=7)
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = today.replace(month=quarter_month, day=1)
    ytd_start = today.replace(month=1, day=1)

    totals: dict[str, dict[str, Decimal]] = {
        "last_week": {},
        "quarter": {},
        "ytd": {},
    }
    start_of_year = datetime.combine(ytd_start, time.min, tzinfo=UTC)
    end_of_today = datetime.combine(today + timedelta(days=1), time.min, tzinfo=UTC)
    for transaction in CurrencyTransaction.objects.filter(
        created_at__gte=start_of_year, created_at__lt=end_of_today, amount__lt=0
    ):
        for period, start in (
            ("last_week", last_week_start),
            ("quarter", quarter_start),
            ("ytd", ytd_start),
        ):
            if transaction.amount and transaction.created_at >= datetime.combine(
                start, time.min, tzinfo=UTC
            ):
                currency = transaction.currency_id
                totals[period][currency] = (
                    totals[period].get(currency, Decimal("0")) - transaction.amount
                )

    return [
        {"key": "last_week", "label": _("Last week"), "totals": totals["last_week"]},
        {"key": "quarter", "label": _("Current quarter"), "totals": totals["quarter"]},
        {"key": "ytd", "label": _("Year to date"), "totals": totals["ytd"]},
    ]
