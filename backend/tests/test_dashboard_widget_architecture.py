"""Contracts for the source/spec/dataset/diagram dashboard architecture."""
from datetime import date
from decimal import Decimal
import inspect

import pytest
from httpx import AsyncClient

from app.models.enums import TransactionType, WidgetDimension, WidgetMetric, WidgetType
from app.schemas.dashboard_widget import DashboardConfig
from app.services.data_sources import (
    DATA_SOURCE_REGISTRY,
    DATA_SPEC_REGISTRY,
    TransactionAnalyticsDataSpec,
    TransactionDataSource,
    get_data_source,
    register_data_source,
)
from app.services.dataset import Dataset, DatasetItem
from app.services.diagrams import DIAGRAM_REGISTRY, BarDiagram, LineDiagram, ListDiagram, PieDiagram
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
        _config(dimension=WidgetDimension.TYPE, transaction_type=TransactionType.EXPENSE),
        _config(dimension=WidgetDimension.CATEGORY, granularity="day"),
        _config(dimension=WidgetDimension.TOTAL, granularity=None),
        _config(dimension=WidgetDimension.ITEM, metric="count"),
        _config(dimension=WidgetDimension.ITEM, metric="sum", granularity="day"),
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


@pytest.mark.parametrize("dimension", ["category", "subcategory", "account", "tag", "type", "total", "item"])
@pytest.mark.parametrize("metric", ["sum", "count"])
def test_transaction_spec_accepts_all_current_dimensions_and_metrics(dimension, metric):
    if dimension == "item" and metric == "count":
        # A raw row is not a group — count is forbidden for "item".
        with pytest.raises(ValueError, match="count"):
            get_data_source("transactions").create_spec("analytics", _config(
                dimension=dimension,
                metric=metric,
                transaction_type=None,
                granularity=None,
            ))
        return
    spec = get_data_source("transactions").create_spec("analytics", _config(
        dimension=dimension,
        metric=metric,
        transaction_type=None if dimension in ("type", "item") else "expense",
        granularity="day" if dimension == "total" else None,
    ))
    assert spec.dimension == dimension
    assert spec.metric == metric


@pytest.mark.parametrize("dimension", ["category", "subcategory", "account", "tag", "total"])
def test_transaction_type_is_optional_for_all_supported_filtered_dimensions(dimension):
    spec = get_data_source("transactions").create_spec("analytics", _config(
        dimension=dimension,
        metric="sum",
        transaction_type=None,
        granularity="day" if dimension == "total" else None,
    ))
    assert spec.dimension == dimension


@pytest.mark.parametrize("transaction_type", [None, "expense", "income", "transfer"])
def test_item_dimension_keeps_transaction_type_an_optional_filter(transaction_type):
    # A raw listing may mix types like the recent-transactions card.
    spec = get_data_source("transactions").create_spec("analytics", _config(
        dimension=WidgetDimension.ITEM,
        metric=WidgetMetric.SUM,
        transaction_type=transaction_type,
    ))
    assert spec.dimension == "item"


def test_legacy_transaction_dimension_alias_still_loads():
    # "transaction" was the pre-release name of the item dimension; a saved
    # dashboard from that iteration must keep rendering, not 500.
    legacy = _widget(query={
        "dimension": "transaction",
        "metric": "sum",
        "filters": {"transaction_type": "expense", "account_id": None},
        "granularity": None,
    })
    config = DashboardConfig.model_validate({"schema_version": 1, "widgets": [legacy]})
    assert config.widgets[0].query.dimension == WidgetDimension.ITEM


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


def _list_dataset(*values) -> Dataset:
    return Dataset(
        items=[
            DatasetItem(element_id=index + 1, key=f"item:{index + 1}", name=f"Item {index + 1}", value=Decimal(value))
            for index, value in enumerate(values)
        ]
    )


def test_list_diagram_is_registered_as_a_categorical_diagram():
    assert DIAGRAM_REGISTRY[WidgetType.LIST] is ListDiagram
    assert ListDiagram.type == WidgetType.LIST
    assert ListDiagram.dataset_kind == "categorical"


def test_list_diagram_sort_none_keeps_source_order():
    dataset = _list_dataset(3, 30, 7)
    assert [point.label for point in ListDiagram().render(dataset).points] == ["Item 1", "Item 2", "Item 3"]
    assert [point.label for point in ListDiagram(sort="none").render(dataset).points] == ["Item 1", "Item 2", "Item 3"]


def test_list_diagram_value_desc_sorts_by_aggregated_value():
    dataset = _list_dataset(3, 30, 7)
    points = ListDiagram(sort="value_desc").render(dataset).points
    assert [point.label for point in points] == ["Item 2", "Item 3", "Item 1"]
    assert [point.value for point in points] == [Decimal("30"), Decimal("7"), Decimal("3")]


def test_list_diagram_value_asc_sorts_by_aggregated_value():
    dataset = _list_dataset(3, 30, 7)
    points = ListDiagram(sort="value_asc").render(dataset).points
    assert [point.label for point in points] == ["Item 1", "Item 3", "Item 2"]
    assert [point.value for point in points] == [Decimal("3"), Decimal("7"), Decimal("30")]


def test_list_diagram_sorts_signed_values_by_numeric_amount():
    dataset = _list_dataset("-1", "-30000", "25")
    points = ListDiagram(sort="value_desc").render(dataset).points
    assert [point.value for point in points] == [Decimal("25"), Decimal("-1"), Decimal("-30000")]


def test_list_diagram_applies_limit_after_value_asc_sorting():
    dataset = _list_dataset("50", "10", "40", "20", "5")
    points = ListDiagram(sort="value_asc", limit=2).render(dataset).points
    assert [point.value for point in points] == [Decimal("5"), Decimal("10")]


@pytest.mark.parametrize("values", [["12.50", "125.00", "40.00"], ["3", "9", "1"]])
def test_list_diagram_sorts_sum_and_count_results_by_the_same_aggregated_value(values):
    # The diagram never sees the metric: sum rows already carry the sum and
    # count rows the count, so sorting by the point's value is sorting by
    # the selected metric in both cases.
    points = ListDiagram(sort="value_desc").render(_list_dataset(*values)).points
    assert [point.value for point in points] == sorted((Decimal(value) for value in values), reverse=True)


def test_list_diagram_applies_limit_after_value_desc_sorting():
    dataset = _list_dataset("50", "10", "40", "20", "5")
    points = ListDiagram(sort="value_desc", limit=2).render(dataset).points
    assert [point.value for point in points] == [Decimal("50"), Decimal("40")]


def test_list_diagram_applies_limit_in_source_order_without_sorting():
    dataset = _list_dataset("50", "10", "40", "20", "5")
    points = ListDiagram(limit=2).render(dataset).points
    assert [point.label for point in points] == ["Item 1", "Item 2"]


def test_list_diagram_defaults_to_an_unsorted_list_of_five_rows():
    dataset = _list_dataset(*[str(index) for index in range(1, 8)])
    diagram = ListDiagram()
    assert (diagram.sort, diagram.limit) == ("none", 5)
    points = diagram.render(dataset).points
    assert [point.label for point in points] == [f"Item {index}" for index in range(1, 6)]


def test_list_diagram_from_options_round_trips_and_defaults_to_none_and_five():
    defaults = ListDiagram.from_options({})
    assert (defaults.sort, defaults.limit) == ("none", 5)
    configured = ListDiagram.from_options({"sort": "value_desc", "limit": 3})
    assert (configured.sort, configured.limit) == ("value_desc", 3)
    explicit_nulls = ListDiagram.from_options({"sort": None, "limit": None})
    assert (explicit_nulls.sort, explicit_nulls.limit) == ("none", 5)


def test_list_diagram_rejects_invalid_sorts_limits_and_unknown_options():
    with pytest.raises(ValueError, match="Unsupported list sort"):
        ListDiagram(sort="alphabetical")
    with pytest.raises(ValueError, match="Unsupported list sort"):
        ListDiagram.from_options({"sort": 5})
    for limit in (0, -1, True, 2.5, "5"):
        with pytest.raises(ValueError, match="positive integer"):
            ListDiagram(limit=limit)
    with pytest.raises(ValueError, match="positive integer"):
        ListDiagram.from_options({"limit": 0})
    with pytest.raises(ValueError, match="does not support"):
        ListDiagram.from_options({"top": 3})


def test_list_diagram_preserves_row_metadata_and_leaves_missing_fields_null():
    dataset = Dataset(
        items=[
            DatasetItem(element_id=7, key="category:7", name="Food", value=Decimal("5"), icon="shopping-basket", color="#1baf7a"),
            DatasetItem(element_id=None, key="diagram:other", name="Other", value=Decimal("2")),
        ]
    )
    points = ListDiagram().render(dataset).points
    assert (points[0].label, points[0].key, points[0].element_id, points[0].icon, points[0].color) == (
        "Food", "category:7", 7, "shopping-basket", "#1baf7a",
    )
    assert (points[1].element_id, points[1].icon, points[1].color) == (None, None, None)


def test_list_diagram_rejects_time_series_datasets():
    with pytest.raises(ValueError, match="categorical"):
        ListDiagram().render(Dataset(kind="time_series"))


def _dashboard_config(*widgets):
    return {"schema_version": 1, "widgets": list(widgets)}


def _widget(widget_id="widget-1", **overrides):
    widget = {
        "id": widget_id,
        "title": "Expenses",
        "data_source": "transactions",
        "data_spec": "analytics",
        "query": {
            "dimension": "category",
            "metric": "sum",
            "filters": {"transaction_type": "expense", "account_id": None},
            "granularity": None,
        },
        "visualization": {"type": "bar", "options": {}},
    }
    widget.update(overrides)
    return widget


async def test_get_and_put_return_separate_config_and_calculated_data(client: AsyncClient, account_id, categories):
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_widget()),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["schema_version"] == 1
    assert body["config"]["widgets"][0]["id"] == "widget-1"
    assert body["widgets"] == [{"id": "widget-1", "data": {"points": []}}]

    await client.post(
        "/transactions",
        json=_txn(account_id, amount="25.00", category_id=categories["Groceries"]["id"], date="2026-08-05"),
    )
    refreshed = await client.get("/dashboard/widgets", params={"year": 2026, "month": 8})
    assert refreshed.status_code == 200
    point = refreshed.json()["widgets"][0]["data"]["points"][0]
    assert money(point["value"]) == Decimal("25.00")
    assert point["key"] == f"category:{categories['Groceries']['id']}"
    assert point["element_id"] == categories["Groceries"]["id"]


async def test_dashboard_config_preserves_widget_order(client: AsyncClient):
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_widget("first"), _widget("second", title="Second")),
    )
    assert response.status_code == 200
    assert [widget["id"] for widget in response.json()["config"]["widgets"]] == ["first", "second"]


async def test_invalid_save_is_atomic_and_keeps_previous_configuration(client: AsyncClient):
    saved = await client.put("/dashboard/widgets?year=2026&month=8", json=_dashboard_config(_widget()))
    assert saved.status_code == 200
    invalid = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config({**_widget(), "data_spec": "missing"}),
    )
    assert invalid.status_code == 400
    current = await client.get("/dashboard/widgets", params={"year": 2026, "month": 8})
    assert [widget["id"] for widget in current.json()["config"]["widgets"]] == ["widget-1"]


async def test_widget_api_preserves_pie_bar_and_line_results(client: AsyncClient, account_id, categories):
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="25.00", category_id=categories["Groceries"]["id"], date="2026-08-05"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="10.00", category_id=categories["Dining Out"]["id"], date="2026-08-06"),
    )

    widgets = [
        _widget("pie", title="Pie", visualization={"type": "pie", "options": {}}),
        _widget("bar", title="Bar"),
        _widget("line", title="Line", query={"dimension": "total", "metric": "sum", "filters": {"transaction_type": "expense", "account_id": None}, "granularity": "day"}, visualization={"type": "line", "options": {}}),
    ]
    response = await client.put("/dashboard/widgets?year=2026&month=8", json=_dashboard_config(*widgets))
    assert response.status_code == 200
    created = response.json()["widgets"]

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
    assert spec["dimensions"] == ["category", "subcategory", "account", "tag", "type", "item", "total"]
    assert spec["metrics"] == ["sum", "count"]
    assert spec["filters"] == ["transaction_type", "account_id", "start_date", "end_date", "granularity"]
    assert spec["required_parameters"] == ["dimension", "metric"]
    assert spec["dimension_kinds"]["total"] == "time_series"
    assert spec["dimension_kinds"]["item"] == "categorical"
    assert spec["required_by_dimension"]["total"] == ["granularity"]
    assert spec["forbidden_by_dimension"]["type"] == ["transaction_type", "granularity"]
    assert spec["forbidden_by_dimension"]["item"] == ["granularity"]
    assert spec["forbidden_metrics_by_dimension"]["item"] == ["count"]
    assert spec["filter_options"]["granularity"] == ["day", "week", "month"]
    assert spec["compatible_diagrams"] == ["pie", "bar", "line", "list"]
    assert {entry["type"] for entry in body["diagrams"]} == {"pie", "bar", "line", "list"}
    diagrams = {entry["type"]: entry for entry in body["diagrams"]}
    assert diagrams["pie"]["allowed_dimensions"] == ["category", "subcategory", "account", "tag", "type"]
    assert diagrams["bar"]["dataset_kind"] == "categorical"
    assert diagrams["bar"]["allowed_dimensions"] == ["category", "subcategory", "account", "tag", "type"]
    assert diagrams["line"]["allowed_dimensions"] == ["total"]
    assert diagrams["line"]["needs_granularity"] is True
    assert diagrams["list"]["dataset_kind"] == "categorical"
    assert diagrams["list"]["allowed_dimensions"] == ["category", "subcategory", "account", "tag", "type", "item"]
    assert diagrams["list"]["allowed_metrics"] == ["sum", "count"]
    assert diagrams["list"]["needs_granularity"] is False
    assert all(entry["compatible_data_specs"] == ["transactions:analytics"] for entry in body["diagrams"])


async def test_widget_endpoint_rejects_unknown_source_spec_and_incompatible_diagram(client: AsyncClient):
    unknown_source = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config({**_widget(), "data_source": "budgets"}),
    )
    assert unknown_source.status_code == 400

    unknown_spec = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config({**_widget(), "data_spec": "missing"}),
    )
    assert unknown_spec.status_code == 400

    invalid_line = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config({**_widget(), "visualization": {"type": "line", "options": {}}}),
    )
    assert invalid_line.status_code == 400

    invalid_type_filter = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config({**_widget(), "query": {"dimension": "type", "metric": "sum", "filters": {"transaction_type": "expense", "account_id": None}, "granularity": None}}),
    )
    assert invalid_type_filter.status_code == 400

    missing_account = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config({**_widget(), "query": {"dimension": "category", "metric": "sum", "filters": {"transaction_type": "expense", "account_id": 999999}, "granularity": None}}),
    )
    assert missing_account.status_code == 400
    assert missing_account.json()["detail"] == "Account not found"


async def test_widget_endpoint_rejects_duplicate_ids(client: AsyncClient):
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_widget("same"), _widget("same")),
    )
    assert response.status_code == 422


async def test_widget_endpoint_rejects_unbounded_configuration_fields(client: AsyncClient):
    invalid = {**_widget(), "unexpected": True}
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(invalid),
    )
    assert response.status_code == 422


def _list_widget(widget_id="list-1", **overrides):
    widget = {
        "id": widget_id,
        "title": "Top categories",
        "data_source": "transactions",
        "data_spec": "analytics",
        "query": {
            "dimension": "category",
            "metric": "sum",
            "filters": {"transaction_type": "expense", "account_id": None},
            "granularity": None,
        },
        "visualization": {"type": "list", "options": {}},
    }
    widget.update(overrides)
    return widget


async def _list_transactions(client: AsyncClient, account_id: int, categories: dict) -> dict:
    """Three August expenses in three categories plus one income and one
    out-of-month transaction that every expense/month filter must exclude."""
    tag = (await client.post("/tags", json={"name": "list-tag"})).json()
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="50.00", category_id=categories["Groceries"]["id"], date="2026-08-01"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="25.00", category_id=categories["Groceries"]["id"], date="2026-08-02"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="40.00", category_id=categories["Dining Out"]["id"], date="2026-08-03", tag_ids=[tag["id"]]),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="10.00", category_id=categories["Dining Out"]["id"], date="2026-07-31"),
    )
    await client.post(
        "/transactions",
        json=_txn(account_id, amount="1000.00", category_id=categories["Salary"]["id"], date="2026-08-04", type="income"),
    )
    return {"tag": tag}


async def test_list_widget_renders_sorted_limited_rows_with_metadata(client: AsyncClient, account_id, categories):
    await _list_transactions(client, account_id, categories)

    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(visualization={"type": "list", "options": {"sort": "value_desc", "limit": 2}})),
    )
    assert response.status_code == 200
    points = response.json()["widgets"][0]["data"]["points"]
    # Numeric descending order: -40 is greater than -75.
    assert [point["label"] for point in points] == ["Dining Out", "Groceries"]
    assert [money(point["value"]) for point in points] == [Decimal("-40.00"), Decimal("-75.00")]
    groceries = points[1]
    assert groceries["key"] == f"category:{categories['Groceries']['id']}"
    assert groceries["element_id"] == categories["Groceries"]["id"]
    assert groceries["icon"] == "shopping-basket"
    assert groceries["color"] == "#1baf7a"


async def test_list_widget_keeps_source_order_and_limits_to_five_by_default(client: AsyncClient, account_id, categories):
    await _list_transactions(client, account_id, categories)

    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget()),
    )
    assert response.status_code == 200
    points = response.json()["widgets"][0]["data"]["points"]
    # No options stored: sort "none" keeps the DataSource order, limit 5.
    assert [point["label"] for point in points] == ["Groceries", "Dining Out"]
    assert [money(point["value"]) for point in points] == [Decimal("-75.00"), Decimal("-40.00")]


@pytest.mark.parametrize("metric", ["sum", "count"])
@pytest.mark.parametrize("dimension", ["category", "subcategory", "account", "tag", "type"])
async def test_list_widget_supports_every_categorical_dimension_and_metric(
    client: AsyncClient, account_id, categories, dimension, metric,
):
    await _list_transactions(client, account_id, categories)
    expected_sum = {
        "category": {"Groceries": -75, "Dining Out": -40},
        "subcategory": {"Groceries": -75, "Dining Out": -40},
        "account": {"Main Account": -115},
        "tag": {"list-tag": -40},
        "type": {"expense": -115, "income": 1000},
    }
    expected_count = {
        "category": {"Groceries": 2, "Dining Out": 1},
        "subcategory": {"Groceries": 2, "Dining Out": 1},
        "account": {"Main Account": 3},
        "tag": {"list-tag": 1},
        "type": {"expense": 3, "income": 1},
    }

    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query={
            "dimension": dimension,
            "metric": metric,
            "filters": {"transaction_type": None if dimension == "type" else "expense", "account_id": None},
            "granularity": None,
        })),
    )
    assert response.status_code == 200
    points = response.json()["widgets"][0]["data"]["points"]
    assert {point["label"]: money(point["value"]) for point in points} == {
        label: Decimal(value)
        for label, value in (expected_sum if metric == "sum" else expected_count)[dimension].items()
    }
    assert all(point["key"] and point["time_bucket"] is None for point in points)


async def test_list_widget_applies_transaction_type_account_and_period_filters(
    client: AsyncClient, account_id, categories,
):
    rows = await _list_transactions(client, account_id, categories)
    other = await client.post("/accounts", json={"name": "Second", "type": "checking"})
    other_id = other.json()["id"]
    await client.post(
        "/transactions",
        json=_txn(other_id, amount="99.00", category_id=categories["Groceries"]["id"], date="2026-08-05", tag_ids=[rows["tag"]["id"]]),
    )

    tag_only = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget("filtered", query={
            "dimension": "tag",
            "metric": "sum",
            "filters": {"transaction_type": "expense", "account_id": account_id},
            "granularity": None,
        })),
    )
    assert tag_only.status_code == 200
    points = tag_only.json()["widgets"][0]["data"]["points"]
    assert [point["label"] for point in points] == ["list-tag"]
    assert money(points[0]["value"]) == Decimal("-40.00")  # The Second-account 99.00 is filtered out.


async def test_list_widget_endpoint_rejects_invalid_options_and_incompatible_dimension(client: AsyncClient):
    invalid_sort = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(visualization={"type": "list", "options": {"sort": "alphabetical"}})),
    )
    assert invalid_sort.status_code == 400

    invalid_limit = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(visualization={"type": "list", "options": {"limit": 0}})),
    )
    assert invalid_limit.status_code == 400

    string_limit = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(visualization={"type": "list", "options": {"limit": "5"}})),
    )
    assert string_limit.status_code == 400

    unknown_option = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(visualization={"type": "list", "options": {"top": 3}})),
    )
    assert unknown_option.status_code == 400

    time_series_dimension = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query={
            "dimension": "total",
            "metric": "sum",
            "filters": {"transaction_type": "expense", "account_id": None},
            "granularity": "day",
        })),
    )
    assert time_series_dimension.status_code == 400


def _item_list_query(metric="sum", transaction_type=None):
    return {
        "dimension": "item",
        "metric": metric,
        "filters": {"transaction_type": transaction_type, "account_id": None},
        "granularity": None,
    }


async def test_list_widget_item_dimension_lists_rows_without_grouping(
    client: AsyncClient, account_id, categories,
):
    await _list_transactions(client, account_id, categories)

    # No options: sort "none" keeps the DataSource's newest-first order, and
    # every row is one item — no aggregation happens.
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query=_item_list_query())),
    )
    assert response.status_code == 200
    points = response.json()["widgets"][0]["data"]["points"]
    assert [money(point["value"]) for point in points] == [
        Decimal("1000.00"),  # Aug 4 income
        Decimal("-40.00"),  # Aug 3 Dining Out
        Decimal("-25.00"),  # Aug 2 Groceries
        Decimal("-50.00"),  # Aug 1 Groceries
    ]
    assert [point["label"] for point in points] == ["Test transaction"] * 4
    assert all(point["key"].startswith("transaction:") for point in points)
    assert all(isinstance(point["element_id"], int) for point in points)
    assert points[1]["icon"] == "utensils"
    assert points[1]["color"] == "#eb6834"


async def test_list_widget_item_dimension_supports_ascending_and_descending_sorts(
    client: AsyncClient, account_id, categories,
):
    await _list_transactions(client, account_id, categories)

    ascending = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget("asc", query=_item_list_query(), visualization={
            "type": "list", "options": {"sort": "value_asc", "limit": 2},
        })),
    )
    assert ascending.status_code == 200
    assert [money(point["value"]) for point in ascending.json()["widgets"][0]["data"]["points"]] == [
        Decimal("-50.00"),
        Decimal("-40.00"),
    ]

    descending = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget("desc", query=_item_list_query(), visualization={
            "type": "list", "options": {"sort": "value_desc", "limit": 2},
        })),
    )
    assert descending.status_code == 200
    assert [money(point["value"]) for point in descending.json()["widgets"][0]["data"]["points"]] == [
        Decimal("1000.00"),
        Decimal("-25.00"),
    ]


async def test_list_widget_item_dimension_applies_optional_type_and_account_filters(
    client: AsyncClient, account_id, categories,
):
    await _list_transactions(client, account_id, categories)

    expenses = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query=_item_list_query(transaction_type="expense"))),
    )
    assert expenses.status_code == 200
    assert [money(point["value"]) for point in expenses.json()["widgets"][0]["data"]["points"]] == [
        Decimal("-40.00"),
        Decimal("-25.00"),
        Decimal("-50.00"),
    ]

    missing_account = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query={
            **_item_list_query(),
            "filters": {"transaction_type": None, "account_id": 999999},
        })),
    )
    assert missing_account.status_code == 400


async def test_list_widget_item_dimension_rejects_the_count_metric(client: AsyncClient):
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query=_item_list_query(metric="count"))),
    )
    assert response.status_code == 400
    assert "count" in response.json()["detail"]


async def test_list_widget_grouped_dimension_accepts_all_transaction_types(client: AsyncClient, account_id, categories):
    await _list_transactions(client, account_id, categories)
    response = await client.put(
        "/dashboard/widgets?year=2026&month=8",
        json=_dashboard_config(_list_widget(query={
            "dimension": "category",
            "metric": "sum",
            "filters": {"transaction_type": None, "account_id": account_id},
            "granularity": None,
        })),
    )
    assert response.status_code == 200
    assert {point["label"] for point in response.json()["widgets"][0]["data"]["points"]} == {
        "Groceries", "Dining Out", "Salary",
    }
