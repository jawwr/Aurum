"""Contracts for the source/spec/dataset/diagram dashboard architecture."""
from datetime import date
from decimal import Decimal
import inspect

import pytest
from httpx import AsyncClient

from app.models.enums import TransactionType, WidgetDimension, WidgetMetric
from app.services.data_sources import (
    DATA_SOURCE_REGISTRY,
    DATA_SPEC_REGISTRY,
    TransactionAnalyticsDataSpec,
    TransactionDataSource,
    get_data_source,
    register_data_source,
)
from app.services.dataset import Dataset, DatasetItem
from app.services.diagrams import BarDiagram, LineDiagram, PieDiagram
import app.services.diagrams as diagrams_module

from tests.helpers import money, txn_payload as _txn


def _config(**overrides):
    config = {
        "dimension": WidgetDimension.CATEGORY,
        "metric": WidgetMetric.SUM,
        "transaction_type": TransactionType.EXPENSE,
        "granularity": None,
        "account_id": None,
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 31),
    }
    config.update(overrides)
    return config


def test_transaction_data_source_is_registered_and_exposes_analytics_spec():
    source = DATA_SOURCE_REGISTRY["transactions"]
    assert isinstance(source, TransactionDataSource)
    assert [spec.id for spec in source.list_specs()] == ["analytics"]
    assert source.list_specs()[0] is TransactionAnalyticsDataSpec
    assert get_data_source("transactions") is source
    assert DATA_SPEC_REGISTRY[("transactions", "analytics")] is TransactionAnalyticsDataSpec
    assert source.create_spec("analytics", _config()).source is source


def test_unknown_source_and_spec_have_explicit_errors():
    with pytest.raises(ValueError, match="Unknown data source"):
        get_data_source("missing")
    with pytest.raises(ValueError, match="Unknown data spec"):
        get_data_source("transactions").create_spec("missing", _config())


def test_registry_rejects_duplicate_and_empty_source_ids():
    with pytest.raises(ValueError, match="already registered"):
        register_data_source(TransactionDataSource())

    class EmptySource(TransactionDataSource):
        id = ""

    with pytest.raises(ValueError, match="non-empty id"):
        register_data_source(EmptySource())


@pytest.mark.parametrize(
    "config",
    [
        _config(dimension="unknown"),
        _config(metric="average"),
        _config(transaction_type=None),
        _config(dimension=WidgetDimension.TYPE, transaction_type=TransactionType.EXPENSE),
        _config(dimension=WidgetDimension.CATEGORY, granularity="day"),
        _config(dimension=WidgetDimension.TOTAL, granularity=None),
        _config(unexpected_filter=True),
        _config(transaction_type="invalid"),
        _config(account_id=True),
        _config(account_id="1"),
        _config(start_date="2026-08-01"),
        _config(start_date=date(2026, 9, 1)),
        _config(dimension=None),
        _config(metric=None),
        _config(dimension="total", granularity="year"),
    ],
)
def test_transaction_spec_rejects_unsupported_dimensions_metrics_and_filters(config):
    with pytest.raises(ValueError):
        DATA_SOURCE_REGISTRY["transactions"].create_spec("analytics", config=config)


@pytest.mark.parametrize("dimension", ["category", "subcategory", "account", "tag", "type", "total"])
@pytest.mark.parametrize("metric", ["sum", "count"])
def test_transaction_spec_accepts_all_current_dimensions_and_metrics(dimension, metric):
    spec = get_data_source("transactions").create_spec("analytics", _config(
        dimension=dimension,
        metric=metric,
        transaction_type=None if dimension == "type" else "expense",
        granularity="day" if dimension == "total" else None,
    ))
    assert spec.dimension == dimension
    assert spec.metric == metric


def test_dataset_supports_stable_keys_metadata_and_aggregate_items():
    categorical = Dataset(
        items=[
            DatasetItem(element_id=7, key="category:7", name="Food", value=Decimal("12.50"), color="#123456"),
            DatasetItem(element_id=None, key="diagram:other", name="Other", value=Decimal("2.50")),
        ]
    )
    time_series = Dataset(
        items=[
            DatasetItem(
                element_id=None,
                key="total:2026-08-01",
                name="Total",
                value=Decimal("15.00"),
                time_bucket=date(2026, 8, 1),
                series_key="total",
            ),
        ],
        kind="time_series",
    )
    assert categorical.items[0].key == "category:7"
    assert categorical.items[1].element_id is None
    assert time_series.items[0].time_bucket == date(2026, 8, 1)
    assert time_series.items[0].series_key == "total"
    assert DatasetItem(element_id=1, key="numeric", name="Numeric", value=10).value == Decimal("10")


def test_diagrams_only_depend_on_dataset_and_not_transaction_orm_models():
    source = inspect.getsource(diagrams_module)
    assert "app.models.transaction" not in source
    assert "from app.models.account" not in source
    assert "from app.models.category" not in source
    assert "Transaction" not in diagrams_module.__dict__
    assert "sqlalchemy" not in source
    assert "AsyncSession" not in source
    assert "select(" not in source
    assert "func." not in source
    assert "app.services.data_sources" not in source
    assert "WidgetDimension" not in source
    assert "WidgetMetric" not in source
    assert "transactions:analytics" not in source


def test_pie_bar_and_line_preserve_visualization_rules():
    categorical = Dataset(
        items=[
            DatasetItem(element_id=index, key=f"item:{index}", name=f"Item {index}", value=Decimal(index))
            for index in range(10, 0, -1)
        ]
    )
    pie = PieDiagram().render(categorical)
    assert len(pie.points) == 9
    assert pie.points[-1].label == "Other"
    assert pie.points[-1].value == Decimal("3")
    assert pie.points[-1].element_id is None
    assert pie.points[-1].color == "#898781"
    assert len(categorical.items) == 10  # Rendering does not modify fetched data.

    bar = BarDiagram().render(
        Dataset(
            items=[
                DatasetItem(element_id=1, key="item:1", name="Small", value=Decimal("2")),
                DatasetItem(element_id=2, key="item:2", name="Large", value=Decimal("8")),
            ]
        )
    )
    assert [point.label for point in bar.points] == ["Large", "Small"]

    line = LineDiagram().render(
        Dataset(
            kind="time_series",
            items=[
                DatasetItem(
                    element_id=None,
                    key="total:2026-08-01",
                    name="Total",
                    value=Decimal("5"),
                    time_bucket=date(2026, 8, 1),
                    series_key="total",
                ),
                DatasetItem(
                    element_id=None,
                    key="total:2026-08-02",
                    name="Total",
                    value=Decimal("7"),
                    time_bucket=date(2026, 8, 2),
                    series_key="total",
                ),
            ],
        )
    )
    assert [point.label for point in line.points] == ["2026-08-01", "2026-08-02"]


def test_dataset_supports_multiple_groups_per_bucket_without_colliding_identity():
    dataset = Dataset(kind="time_series", items=[
        DatasetItem(
            element_id=group,
            key=f"group:{group}:{day.isoformat()}",
            name=name,
            value=Decimal("10"),
            series_key=f"group:{group}",
            time_bucket=day,
        )
        for group, name in [(1, "Food"), (2, "Transport")]
        for day in [date(2026, 8, 1), date(2026, 8, 2)]
    ])
    assert len({item.key for item in dataset.items}) == 4
    assert len({item.series_key for item in dataset.items}) == 2
    with pytest.raises(ValueError, match="single series"):
        LineDiagram().render(dataset)
    with pytest.raises(ValueError, match="categorical"):
        PieDiagram().render(dataset)


def test_dataset_rejects_duplicate_keys_missing_buckets_and_nonfinite_values():
    item = DatasetItem(element_id=None, key="total", name="Total", value=Decimal("1"))
    with pytest.raises(ValueError, match="unique"):
        Dataset(items=[item, item])
    with pytest.raises(ValueError, match="bucket"):
        Dataset(kind="time_series", items=[item])
    with pytest.raises(ValueError, match="finite Decimal"):
        DatasetItem(element_id=None, key="bad", name="Bad", value=Decimal("NaN"))
    assert Dataset().items == []
    assert LineDiagram().render(Dataset(kind="time_series")).points == []


async def test_existing_widget_payload_defaults_to_transactions_analytics(client: AsyncClient, account_id, categories):
    response = await client.post(
        "/dashboard/widgets?year=2026&month=8",
        json={
            "type": "bar",
            "title": "Expenses",
            "dimension": "category",
            "metric": "sum",
            "transaction_type": "expense",
            "granularity": None,
            "account_id": None,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["data_source"] == "transactions"
    assert body["data_spec"] == "analytics"
    assert body["data"]["points"] == []

    await client.post(
        "/transactions",
        json=_txn(account_id, amount="25.00", category_id=categories["Groceries"]["id"], date="2026-08-05"),
    )
    refreshed = await client.get("/dashboard/widgets", params={"year": 2026, "month": 8})
    assert refreshed.status_code == 200
    point = refreshed.json()[0]["data"]["points"][0]
    assert money(point["value"]) == Decimal("25.00")
    assert point["key"] == f"category:{categories['Groceries']['id']}"
    assert point["element_id"] == categories["Groceries"]["id"]


async def test_widget_api_preserves_pie_bar_and_line_results(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="25.00", category_id=categories["Groceries"]["id"], date="2026-08-05"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="10.00", category_id=categories["Dining Out"]["id"], date="2026-08-06"),
    )

    common = {
        "metric": "sum",
        "transaction_type": "expense",
        "granularity": None,
        "account_id": None,
    }
    created = []
    for widget in [
        {"type": "pie", "title": "Pie", "dimension": "category"},
        {"type": "bar", "title": "Bar", "dimension": "category"},
        {"type": "line", "title": "Line", "dimension": "total", "granularity": "day"},
    ]:
        response = await client.post(
            "/dashboard/widgets?year=2026&month=8",
            json={**common, **widget},
        )
        assert response.status_code == 201
        created.append(response.json())

    assert {point["label"]: money(point["value"]) for point in created[0]["data"]["points"]} == {
        "Groceries": Decimal("25.00"),
        "Dining Out": Decimal("10.00"),
    }
    assert [point["label"] for point in created[1]["data"]["points"]] == ["Groceries", "Dining Out"]
    assert [money(point["value"]) for point in created[2]["data"]["points"]] == [Decimal("25.00"), Decimal("10.00")]
    assert [point["label"] for point in created[2]["data"]["points"]] == ["2026-08-05", "2026-08-06"]


async def test_widget_manifest_describes_sources_specs_and_visualization_compatibility(client: AsyncClient):
    response = await client.get("/dashboard/widgets/types")
    assert response.status_code == 200
    body = response.json()
    source = body["data_sources"][0]
    spec = source["specifications"][0]
    assert source["id"] == "transactions"
    assert spec["id"] == "analytics"
    assert spec["dimensions"] == ["category", "subcategory", "account", "tag", "type", "total"]
    assert spec["metrics"] == ["sum", "count"]
    assert spec["filters"] == ["transaction_type", "account_id", "start_date", "end_date", "granularity"]
    assert spec["required_parameters"] == ["dimension", "metric"]
    assert spec["dimension_kinds"]["total"] == "time_series"
    assert spec["required_by_dimension"]["total"] == ["transaction_type", "granularity"]
    assert spec["forbidden_by_dimension"]["type"] == ["transaction_type", "granularity"]
    assert spec["filter_options"]["granularity"] == ["day", "week", "month"]
    assert spec["compatible_diagrams"] == ["pie", "bar", "line"]
    assert {entry["type"] for entry in body["diagrams"]} == {"pie", "bar", "line"}
    diagrams = {entry["type"]: entry for entry in body["diagrams"]}
    assert diagrams["pie"]["allowed_dimensions"] == ["category", "subcategory", "account", "tag", "type"]
    assert diagrams["bar"]["dataset_kind"] == "categorical"
    assert diagrams["line"]["allowed_dimensions"] == ["total"]
    assert diagrams["line"]["needs_granularity"] is True
    assert all(entry["compatible_data_specs"] == ["transactions:analytics"] for entry in body["diagrams"])


async def test_widget_endpoint_rejects_unknown_source_spec_and_incompatible_diagram(client: AsyncClient):
    payload = {
        "type": "pie",
        "title": "Invalid",
        "dimension": "category",
        "metric": "sum",
        "transaction_type": "expense",
        "granularity": None,
        "account_id": None,
    }

    unknown_source = await client.post(
        "/dashboard/widgets?year=2026&month=8",
        json={**payload, "data_source": "budgets"},
    )
    assert unknown_source.status_code == 400

    unknown_spec = await client.post(
        "/dashboard/widgets?year=2026&month=8",
        json={**payload, "data_spec": "missing"},
    )
    assert unknown_spec.status_code == 400

    invalid_line = await client.post(
        "/dashboard/widgets?year=2026&month=8",
        json={**payload, "type": "line"},
    )
    assert invalid_line.status_code == 400

    invalid_type_filter = await client.post(
        "/dashboard/widgets?year=2026&month=8",
        json={**payload, "dimension": "type", "transaction_type": "expense"},
    )
    assert invalid_type_filter.status_code == 400

    missing_account = await client.post(
        "/dashboard/widgets?year=2026&month=8",
        json={**payload, "account_id": 999999},
    )
    assert missing_account.status_code == 400
    assert missing_account.json()["detail"] == "Account not found"


async def test_widget_endpoint_returns_not_found_for_missing_widget(client: AsyncClient):
    payload = {
        "type": "bar",
        "title": "Missing",
        "dimension": "category",
        "metric": "sum",
        "transaction_type": "expense",
        "granularity": None,
        "account_id": None,
    }
    patched = await client.patch("/dashboard/widgets/999999?year=2026&month=8", json=payload)
    assert patched.status_code == 404
    deleted = await client.delete("/dashboard/widgets/999999")
    assert deleted.status_code == 404
