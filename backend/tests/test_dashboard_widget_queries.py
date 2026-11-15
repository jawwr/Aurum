"""Financial regressions for transaction Dataset queries, including time buckets."""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.account import Account
from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType
from app.models.tag import Tag
from app.models.transaction import Transaction, TransactionSplit
from app.services.data_sources import get_data_source
from app.services.diagrams import LineDiagram, ListDiagram


@pytest_asyncio.fixture
async def analytics_rows(account_id, categories, test_sessionmaker):
    parent_id = categories["Groceries"]["id"]
    async with test_sessionmaker() as session:
        account = await session.get(Account, account_id)
        account.name = "Selected"
        account.color = "#123456"
        other = Account(name="Other", color="#654321")
        child = Category(name="Leaf", kind=CategoryKind.EXPENSE, parent_id=parent_id, color="#abcdef", icon="Candy")
        parent = await session.get(Category, parent_id)
        parent.icon = "ShoppingBasket"
        shared = Tag(name="Shared")
        extra = Tag(name="Extra")
        session.add_all([other, child, shared, extra])
        await session.flush()

        def transaction(amount, day, *, account=account_id, category=parent_id, kind=TransactionType.EXPENSE, **fields):
            return Transaction(
                account_id=account, category_id=category, amount=Decimal(amount),
                type=kind, description="Analytics regression", date=day, tags=[shared], **fields,
            )

        split = transaction("50", date(2026, 8, 1), category=None)
        split.tags.append(extra)
        split.splits = [
            TransactionSplit(category_id=parent_id, amount=Decimal("20")),
            TransactionSplit(category_id=child.id, amount=Decimal("20")),
            TransactionSplit(category_id=child.id, amount=Decimal("10")),
        ]
        session.add_all([
            transaction("10", date(2026, 8, 1), category=child.id),
            split,
            transaction("30", date(2026, 8, 31)),
            transaction("999", date(2026, 7, 31)),
            transaction("999", date(2026, 9, 1)),
            transaction("100", date(2026, 8, 1), account=other.id),
            transaction("1000", date(2026, 8, 1), category=categories["Salary"]["id"], kind=TransactionType.INCOME),
            transaction("7", date(2026, 8, 1), category=None, kind=TransactionType.TRANSFER, transfer_account_id=other.id),
        ])
        await session.commit()
        return {
            "account": account_id, "other": other.id, "parent": parent_id, "child": child.id,
            "parent_color": parent.color, "shared_tag": shared.id, "extra_tag": extra.id,
        }


def _spec(rows, dimension, metric="sum", **overrides):
    config = {
        "dimension": dimension, "metric": metric,
        "transaction_type": None if dimension == "type" else "expense",
        "granularity": "day" if dimension == "total" else None,
        "account_id": rows["account"], "start_date": date(2026, 8, 1), "end_date": date(2026, 8, 31),
    }
    config.update(overrides)
    return get_data_source("transactions").create_spec("analytics", config)


@pytest.mark.parametrize("metric", ["sum", "count"])
@pytest.mark.parametrize("dimension", ["category", "subcategory", "account", "tag", "type"])
async def test_all_transaction_dimensions_preserve_aggregation_and_query_filters(
    test_sessionmaker, analytics_rows, dimension, metric,
):
    rows = analytics_rows
    expected_sum = {
        "category": {"Groceries": 90},
        "subcategory": {"Groceries": 50, "Leaf": 40},
        "account": {"Selected": 90},
        "tag": {"Shared": 90, "Extra": 50},
        "type": {"expense": 190, "income": 1000, "transfer": 7},
    }
    expected_count = {
        "category": {"Groceries": 3},
        "subcategory": {"Groceries": 2, "Leaf": 2},
        "account": {"Selected": 3},
        "tag": {"Shared": 3, "Extra": 1},
        "type": {"expense": 4, "income": 1, "transfer": 1},
    }
    async with test_sessionmaker() as session:
        dataset = await _spec(
            rows,
            dimension,
            metric,
            account_id=None if dimension == "type" else rows["account"],
        ).fetch(session)
        assert {item.name: item.value for item in dataset.items} == (
            expected_sum if metric == "sum" else expected_count
        )[dimension]
        assert len({item.key for item in dataset.items}) == len(dataset.items)
        assert all(item.element_id is not None for item in dataset.items)
        assert (await _spec(rows, dimension, metric, account_id=-1).fetch(session)).items == []


async def test_dataset_preserves_source_colors_icons_and_entity_identity(test_sessionmaker, analytics_rows):
    rows = analytics_rows
    async with test_sessionmaker() as session:
        category = (await _spec(rows, "category").fetch(session)).items[0]
        assert (category.element_id, category.key, category.icon, category.color) == (
            rows["parent"], f"category:{rows['parent']}", "ShoppingBasket", rows["parent_color"],
        )
        account = (await _spec(rows, "account").fetch(session)).items[0]
        assert account.element_id == rows["account"]
        assert account.color == "#123456"
        tags = (await _spec(rows, "tag").fetch(session)).items
        assert all(item.color is None for item in tags)
        types = (await _spec(rows, "type", account_id=None).fetch(session)).items
        assert {item.name: item.color for item in types} == {
            "income": "#3aa76d", "expense": "#d6564a", "transfer": "#898781",
        }


@pytest.mark.parametrize("metric,values", [("sum", [60, 30]), ("count", [2, 1])])
@pytest.mark.parametrize("granularity,labels", [
    ("day", ["2026-08-01", "2026-08-31"]),
    ("week", ["2026-07-27", "2026-08-31"]),
])
async def test_time_buckets_filter_transactions_before_aggregation(
    test_sessionmaker, analytics_rows, metric, values, granularity, labels,
):
    async with test_sessionmaker() as session:
        dataset = await _spec(analytics_rows, "total", metric, granularity=granularity).fetch(session)
        points = LineDiagram().render(dataset).points
        assert [point.label for point in points] == labels
        assert [point.value for point in points] == values
        assert all(point.series_key == "total" and point.element_id is None for point in points)


async def test_transaction_dimension_lists_unaggregated_rows_newest_first(test_sessionmaker, analytics_rows):
    rows = analytics_rows
    async with test_sessionmaker() as session:
        dataset = await _spec(rows, "item").fetch(session)
        assert dataset.kind == "categorical"
        # Newest first (date desc, then id desc); each row is one whole
        # transaction — its own amount, not an aggregate.
        assert [(item.element_id, item.value) for item in dataset.items] == [
            (3, Decimal("30")),  # Aug 31
            (2, Decimal("50")),  # Aug 1 split — no category of its own
            (1, Decimal("10")),  # Aug 1 leaf-category transaction
        ]
        assert all(item.name == "Analytics regression" for item in dataset.items)
        assert all(item.key == f"transaction:{item.element_id}" for item in dataset.items)
        # Category metadata rides along when the transaction has a category;
        # the split's null category stays null (no invented icon/color).
        assert (dataset.items[0].icon, dataset.items[0].color) == ("ShoppingBasket", rows["parent_color"])
        assert (dataset.items[1].icon, dataset.items[1].color) == (None, None)
        assert (dataset.items[2].icon, dataset.items[2].color) == ("Candy", "#abcdef")
        assert (await _spec(rows, "item", account_id=-1).fetch(session)).items == []


async def test_item_dimension_type_filter_is_optional_and_applies_before_listing(
    test_sessionmaker, analytics_rows,
):
    rows = analytics_rows
    async with test_sessionmaker() as session:
        all_types = await _spec(rows, "item", transaction_type=None).fetch(session)
        # Income (1000) and the transfer (7) join the listing when no type
        # filter is set, still newest-first within each date.
        assert [item.value for item in all_types.items] == [
            Decimal("30"),  # Aug 31 expense
            Decimal("7"),  # Aug 1 transfer (id 8)
            Decimal("1000"),  # Aug 1 income (id 7)
            Decimal("50"),  # Aug 1 split (id 2)
            Decimal("10"),  # Aug 1 expense (id 1)
        ]
        income_only = await _spec(rows, "item", transaction_type="income").fetch(session)
        assert [item.value for item in income_only.items] == [Decimal("1000")]


async def test_grouped_dimensions_accept_all_transaction_types_before_aggregation(test_sessionmaker, analytics_rows):
    async with test_sessionmaker() as session:
        dataset = await _spec(analytics_rows, "category", transaction_type=None, account_id=None).fetch(session)
        assert {item.name: item.value for item in dataset.items} == {
            "Groceries": Decimal("190"),  # Includes the other account's 100.
            "Salary": Decimal("1000"),
        }
        subcategories = await _spec(analytics_rows, "subcategory", "count", transaction_type=None).fetch(session)
        assert {item.name: item.value for item in subcategories.items} == {
            "Groceries": 2, "Leaf": 2, "Salary": 1,
        }
        account = await _spec(analytics_rows, "account", transaction_type=None).fetch(session)
        assert {item.name: item.value for item in account.items} == {
            "Selected": Decimal("1097"), "Other": Decimal("100"),
        }
        totals = await _spec(analytics_rows, "total", transaction_type=None, granularity="month").fetch(session)
        assert totals.items[0].value == Decimal("1197")
        transfers = await _spec(analytics_rows, "item", transaction_type="transfer").fetch(session)
        assert [item.value for item in transfers.items] == [Decimal("7")]


async def test_list_diagram_sorts_item_rows_both_directions(test_sessionmaker, analytics_rows):
    rows = analytics_rows
    async with test_sessionmaker() as session:
        dataset = await _spec(rows, "item", transaction_type=None).fetch(session)
    ascending = ListDiagram(sort="value_asc").render(dataset)
    assert [point.value for point in ascending.points] == [
        Decimal("7"), Decimal("10"), Decimal("30"), Decimal("50"), Decimal("1000"),
    ]
    top_two = ListDiagram(sort="value_desc", limit=2).render(dataset)
    assert [point.value for point in top_two.points] == [Decimal("1000"), Decimal("50")]


async def test_list_data_spec_preserves_transaction_signs_for_sum(test_sessionmaker, analytics_rows):
    async with test_sessionmaker() as session:
        dataset = await _spec(analytics_rows, "item", transaction_type=None, signed_amounts=True).fetch(session)
        assert [item.value for item in dataset.items] == [
            Decimal("-30"), Decimal("7"), Decimal("1000"), Decimal("-50"), Decimal("-10"),
        ]
        categories = await _spec(
            analytics_rows, "category", transaction_type="expense", signed_amounts=True,
        ).fetch(session)
        assert {item.name: item.value for item in categories.items} == {"Groceries": Decimal("-90")}


async def test_signed_category_contributions_are_cast_and_signed_in_sql(
    test_sessionmaker, analytics_rows,
):
    async with test_sessionmaker() as session:
        dataset = await _spec(
            analytics_rows, "category", transaction_type=None, account_id=None, signed_amounts=True,
        ).fetch(session)

        assert {item.name: item.value for item in dataset.items} == {
            "Groceries": Decimal("-190"),  # Includes the other account's 100.
            "Salary": Decimal("1000"),
        }


async def test_signed_item_values_are_sorted_by_numeric_amount_not_absolute_amount(
    test_sessionmaker, analytics_rows,
):
    async with test_sessionmaker() as session:
        dataset = await _spec(analytics_rows, "item", transaction_type=None, signed_amounts=True).fetch(session)

        descending = ListDiagram(sort="value_desc").render(dataset).points
        ascending = ListDiagram(sort="value_asc").render(dataset).points

        assert [point.value for point in descending] == [
            Decimal("1000"), Decimal("7"), Decimal("-10"), Decimal("-30"), Decimal("-50"),
        ]
        assert [point.value for point in ascending] == [
            Decimal("-50"), Decimal("-30"), Decimal("-10"), Decimal("7"), Decimal("1000"),
        ]


@pytest.mark.parametrize("metric,value", [("sum", 90), ("count", 3)])
async def test_month_bucket_and_no_account_filter(test_sessionmaker, analytics_rows, metric, value):
    async with test_sessionmaker() as session:
        dataset = await _spec(analytics_rows, "total", metric, granularity="month").fetch(session)
        assert [(item.time_bucket, item.value) for item in dataset.items] == [(date(2026, 8, 1), value)]
        all_accounts = await _spec(analytics_rows, "total", metric, granularity="month", account_id=None).fetch(session)
        assert all_accounts.items[0].value == (190 if metric == "sum" else 4)
