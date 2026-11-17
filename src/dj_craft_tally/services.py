"""Reusable domain services for inventory and workshop reporting."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TypedDict

from django.db.models import Case, Sum, When
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.models import MaterialLot


class TotalForPeriod(TypedDict):
    key: str
    label: str
    totals: dict[str, Decimal]


def expenditure_periods(*, as_of: date | None = None) -> list[TotalForPeriod]:
    """Return material purchase totals for common reporting periods.

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

    expenditure_data = (
        MaterialLot.objects.filter(
            received_at__gte=datetime.combine(ytd_start, time.min, tzinfo=UTC),
            purchase_amount__isnull=False,
        )
        .values("purchase_currency_id")
        .annotate(
            last_week=Sum(
                Case(
                    When(
                        received_at__gte=datetime.combine(
                            last_week_start, time.min, tzinfo=UTC
                        ),
                        then="purchase_amount",
                    ),
                    default=Decimal("0"),
                )
            ),
            quarter=Sum(
                Case(
                    When(
                        received_at__gte=datetime.combine(
                            quarter_start, time.min, tzinfo=UTC
                        ),
                        then="purchase_amount",
                    ),
                    default=Decimal("0"),
                )
            ),
            ytd=Sum("purchase_amount"),
        )
    )

    totals: dict[str, dict[str, Decimal]] = {
        "last_week": {},
        "quarter": {},
        "ytd": {},
    }
    for row in expenditure_data:
        code = row["purchase_currency_id"]
        for period, period_totals in totals.items():
            if row[period]:
                period_totals[code] = row[period]

    return [
        {"key": "last_week", "label": _("Last week"), "totals": totals["last_week"]},
        {"key": "quarter", "label": _("Current quarter"), "totals": totals["quarter"]},
        {"key": "ytd", "label": _("Year to date"), "totals": totals["ytd"]},
    ]
