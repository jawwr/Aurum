"""Account filtering for split-aware widget category aggregation."""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.enums import TransactionType, WidgetDimension, WidgetMetric
from app.models.transaction import Transaction, TransactionSplit
from app.services.category_rollup import raw_category_contributions, rollup_spending_by_top_level_category
from app.services.diagrams import BarDiagram, PieDiagram


@pytest_asyncio.fixture
async def category_transactions(client: AsyncClient, account_id, categories, test_sessionmaker):
    other = await client.post("/accounts", json={"name": "Savings", "type": "savings", "currency": "USD"})
    assert other.status_code == 201
    parent = categories["Groceries"]["id"]
    child_response = await client.post(
        "/categories", json={"name": "Sweets", "kind": "expense", "color": "#7a869a", "parent_id": parent}
    )
    assert child_response.status_code == 201
    child = child_response.json()["id"]
    other_id = other.json()["id"]

    async with test_sessionmaker() as session:
        def transaction(account, amount, category, day=date(2026, 8, 15), kind=TransactionType.EXPENSE):
            return Transaction(account_id=account, amount=Decimal(amount), category_id=category,
                               type=kind, description="test", date=day)

        selected_plain = transaction(account_id, "10", child)
        selected_split = transaction(account_id, "50", None)
        selected_split.splits = [
            TransactionSplit(category_id=parent, amount=Decimal("20")),
            TransactionSplit(category_id=child, amount=Decimal("20")),
            TransactionSplit(category_id=child, amount=Decimal("10")),
        ]
        other_plain = transaction(other_id, "100", parent)
        other_split = transaction(other_id, "100", None)
        other_split.splits = [
            TransactionSplit(category_id=parent, amount=Decimal("40")),
            TransactionSplit(category_id=child, amount=Decimal("60")),
        ]
        session.add_all([
            selected_plain, selected_split, other_plain, other_split,
            transaction(account_id, "999", parent, day=date(2026, 9, 1)),
            transaction(account_id, "999", parent, kind=TransactionType.INCOME),
        ])
        await session.commit()
    return account_id, other_id


@pytest.mark.parametrize("diagram_cls", [BarDiagram, PieDiagram])
@pytest.mark.parametrize(
    "dimension,metric,selected,all_accounts",
    [
        (WidgetDimension.CATEGORY, WidgetMetric.SUM, {"Groceries": 60}, {"Groceries": 260}),
        (WidgetDimension.SUBCATEGORY, WidgetMetric.SUM, {"Groceries": 20, "Sweets": 40},
         {"Groceries": 160, "Sweets": 100}),
        (WidgetDimension.CATEGORY, WidgetMetric.COUNT, {"Groceries": 2}, {"Groceries": 4}),
        (WidgetDimension.SUBCATEGORY, WidgetMetric.COUNT, {"Groceries": 1, "Sweets": 2},
         {"Groceries": 3, "Sweets": 3}),
    ],
)
async def test_category_widget_account_filter(
    test_sessionmaker, category_transactions, diagram_cls, dimension, metric, selected, all_accounts
):
    account_id, _ = category_transactions
    async with test_sessionmaker() as session:
        for account_filter, expected in [(account_id, selected), (None, all_accounts), (-1, {})]:
            diagram = diagram_cls(
                dimension=dimension, metric=metric, transaction_type=TransactionType.EXPENSE,
                granularity=None, account_id=account_filter, start=date(2026, 8, 1), end=date(2026, 8, 31),
            )
            data = await diagram.fetch(session)
            assert {point.label: point.value for point in data.points} == expected


async def test_rollup_optional_account_and_parent_children(test_sessionmaker, category_transactions):
    account_id, other_id = category_transactions
    dates = {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31)}
    async with test_sessionmaker() as session:
        raw_args = {"transaction_type": TransactionType.EXPENSE, **dates}
        assert await raw_category_contributions(session, **raw_args) == await raw_category_contributions(
            session, **raw_args, account_id=None
        )
        assert await rollup_spending_by_top_level_category(session, **raw_args) == (
            await rollup_spending_by_top_level_category(session, **raw_args, account_id=None)
        )
        selected = await rollup_spending_by_top_level_category(session, **raw_args, account_id=account_id)
        assert len(selected) == 1
        assert selected[0].name == "Groceries"
        assert selected[0].amount == Decimal("60")
        assert selected[0].transaction_count == 2
        assert {child.name: child.amount for child in selected[0].children} == {
            "Groceries": Decimal("20"), "Sweets": Decimal("40")
        }
        other = await rollup_spending_by_top_level_category(session, **raw_args, account_id=other_id)
        assert other[0].amount == Decimal("200")
        assert other[0].transaction_count == 2
        assert len(await raw_category_contributions(session, **raw_args, account_id=account_id)) == 4
