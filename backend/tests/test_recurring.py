"""Recurring transactions: a template can be posted only once per period."""
from datetime import date

from httpx import AsyncClient

from app.models.enums import RecurringFrequency
from app.models.recurring import RecurringTransaction
from app.services.recurring_service import _is_paid_in_current_period


async def _recurring(client: AsyncClient, account_id: int, frequency: str = "monthly") -> dict:
    resp = await client.post(
        "/recurring",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "100",
            "description": "Rent",
            "frequency": frequency,
            "anchor_date": date.today().isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def test_second_post_in_same_period_is_rejected(client: AsyncClient, account_id: int):
    recurring = await _recurring(client, account_id)
    assert recurring["is_paid_current_period"] is False

    first = await client.post(f"/recurring/{recurring['id']}/post")
    second = await client.post(f"/recurring/{recurring['id']}/post")

    assert first.status_code == 201
    assert first.json()["is_paid_current_period"] is True
    assert second.status_code == 409
    transactions = (await client.get("/transactions")).json()
    items = transactions["items"] if isinstance(transactions, dict) else transactions
    assert len([t for t in items if t["description"] == "Rent"]) == 1


def test_paid_flag_resets_when_a_new_month_starts():
    recurring = RecurringTransaction(frequency=RecurringFrequency.MONTHLY, last_posted_date=date(2026, 1, 31))

    assert _is_paid_in_current_period(recurring, date(2026, 1, 31)) is True
    assert _is_paid_in_current_period(recurring, date(2026, 2, 1)) is False
    # Same month number, different year is a new period too.
    assert _is_paid_in_current_period(recurring, date(2027, 1, 15)) is False


def test_paid_flag_for_weekly_and_yearly():
    weekly = RecurringTransaction(frequency=RecurringFrequency.WEEKLY, last_posted_date=date(2026, 1, 7))  # Wed
    assert _is_paid_in_current_period(weekly, date(2026, 1, 11)) is True  # Sunday, same ISO week
    assert _is_paid_in_current_period(weekly, date(2026, 1, 12)) is False  # next Monday

    yearly = RecurringTransaction(frequency=RecurringFrequency.YEARLY, last_posted_date=date(2026, 3, 1))
    assert _is_paid_in_current_period(yearly, date(2026, 12, 31)) is True
    assert _is_paid_in_current_period(yearly, date(2027, 1, 1)) is False


def test_never_posted_is_not_paid():
    recurring = RecurringTransaction(frequency=RecurringFrequency.MONTHLY, last_posted_date=None)
    assert _is_paid_in_current_period(recurring, date(2026, 1, 1)) is False
