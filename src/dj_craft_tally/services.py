"""Reusable domain services for inventory and workshop reporting."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TypedDict

from django.utils.translation import gettext_lazy as _

from dj_craft_tally.models import CurrencyTransaction


class TotalForPeriod(TypedDict):
    key: str
    label: str
    totals: dict[str, Decimal]


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
