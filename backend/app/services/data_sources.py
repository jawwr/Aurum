"""Data sources and data specifications for dashboard widgets.

This module owns transaction queries and the conversion of query results into
the source-neutral :class:`~app.services.dataset.Dataset`.  Visualization
code lives in ``diagrams.py`` and only receives that dataset.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.tag import Tag, transaction_tags
from app.models.transaction import Transaction
from app.services.category_rollup import raw_category_contributions, rollup_spending_by_top_level_category
from app.services.dataset import Dataset, DatasetItem, DatasetKind


def _value(value: Any) -> Any:
    """Return an enum's wire value while accepting plain strings too."""

    return value.value if hasattr(value, "value") else value


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)


def _metric_column(metric: str):
    return func.sum(Transaction.amount) if metric == "sum" else func.count(Transaction.id)


def _date_value(value: date_ | datetime) -> date_:
    return value.date() if isinstance(value, datetime) else value


class DataSpec(ABC):
    """A validated, configured query against one :class:`DataSource`."""

    id: str
    dimensions: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    supported_filters: tuple[str, ...] = ()
    required_parameters: tuple[str, ...] = ()
    dimension_kinds: Mapping[str, DatasetKind] = {}
    required_by_dimension: Mapping[str, tuple[str, ...]] = {}
    forbidden_by_dimension: Mapping[str, tuple[str, ...]] = {}
    filter_options: Mapping[str, tuple[str, ...]] = {}
    source: DataSource

    def __init__(self, *, source: DataSource, config: Mapping[str, Any]) -> None:
        self.source = source
        self.config = dict(config)
        self.validate_config(self.config)

    @classmethod
    def result_kind(cls, dimension: str) -> DatasetKind:
        try:
            return cls.dimension_kinds[_value(dimension)]
        except KeyError as exc:
            raise ValueError(f"Unsupported dimension '{dimension}'") from exc

    async def validate_references(self, session: AsyncSession) -> None:
        await self.source.validate_references(session, self.config)

    @classmethod
    @abstractmethod
    def validate_config(cls, config: Mapping[str, Any]) -> None:
        """Validate a configuration before a query can be executed."""

    @abstractmethod
    async def fetch(self, session: AsyncSession) -> Dataset:
        """Execute this specification and return source-neutral data."""


class DataSource(ABC):
    """Registry-backed provider of one or more data specifications."""

    id: str
    spec_classes: dict[str, type[DataSpec]] = {}

    def __init__(self) -> None:
        self.spec_classes = dict(self.spec_classes)

    def list_specs(self) -> list[type[DataSpec]]:
        return list(self.spec_classes.values())

    def create_spec(self, spec_id: str, config: Mapping[str, Any]) -> DataSpec:
        spec_cls = self.spec_classes.get(spec_id)
        if spec_cls is None:
            raise ValueError(f"Unknown data spec '{self.id}:{spec_id}'")
        return spec_cls(source=self, config=config)

    async def validate_references(self, session: AsyncSession, config: Mapping[str, Any]) -> None:
        """Optional source-level validation of referenced entities."""


class TransactionAnalyticsDataSpec(DataSpec):
    """Aggregated transaction data used by the current dashboard widgets."""

    id = "analytics"
    dimensions = ("category", "subcategory", "account", "tag", "type", "total")
    metrics = ("sum", "count")
    supported_filters = ("transaction_type", "account_id", "start_date", "end_date", "granularity")
    required_parameters = ("dimension", "metric")
    dimension_kinds: Mapping[str, DatasetKind] = {
        "category": "categorical",
        "subcategory": "categorical",
        "account": "categorical",
        "tag": "categorical",
        "type": "categorical",
        "total": "time_series",
    }
    required_by_dimension = {
        "category": ("transaction_type",),
        "subcategory": ("transaction_type",),
        "account": ("transaction_type",),
        "tag": ("transaction_type",),
        "total": ("transaction_type", "granularity"),
    }
    forbidden_by_dimension = {
        "category": ("granularity",),
        "subcategory": ("granularity",),
        "account": ("granularity",),
        "tag": ("granularity",),
        "type": ("transaction_type", "granularity"),
    }
    filter_options = {
        "transaction_type": ("expense", "income", "transfer"),
        "granularity": ("day", "week", "month"),
    }
    source: TransactionDataSource

    @classmethod
    def validate_config(cls, config: Mapping[str, Any]) -> None:
        allowed = set(cls.required_parameters) | set(cls.supported_filters)
        unknown = sorted(set(config) - allowed)
        if unknown:
            raise ValueError(f"Unsupported filter or parameter '{unknown[0]}'")

        missing = [name for name in cls.required_parameters if config.get(name) is None]
        if missing:
            raise ValueError(f"'{missing[0]}' is required for the transactions analytics spec")

        dimension = _value(config["dimension"])
        metric = _value(config["metric"])
        if dimension not in cls.dimensions:
            raise ValueError(f"'{dimension}' is not a supported transaction dimension")
        if metric not in cls.metrics:
            raise ValueError(f"'{metric}' is not a supported transaction metric")

        for name in cls.required_by_dimension.get(dimension, ()):
            if config.get(name) is None:
                raise ValueError(f"{name} is required for dimension '{dimension}'")
        for name in cls.forbidden_by_dimension.get(dimension, ()):
            if config.get(name) is not None:
                raise ValueError(f"{name} must be omitted for dimension '{dimension}'")
        for name, options in cls.filter_options.items():
            if config.get(name) is not None and _value(config[name]) not in options:
                raise ValueError(f"{name} is not supported")

        account_id = config.get("account_id")
        if account_id is not None and (isinstance(account_id, bool) or not isinstance(account_id, int)):
            raise ValueError("account_id must be an integer")

        for name in ("start_date", "end_date"):
            value = config.get(name)
            if value is not None and type(value) is not date_:
                raise ValueError(f"{name} must be a date")
        if config.get("start_date") is not None and config.get("end_date") is not None:
            if config["start_date"] > config["end_date"]:
                raise ValueError("start_date must not be after end_date")

    @property
    def dimension(self) -> str:
        return _value(self.config["dimension"])

    @property
    def metric(self) -> str:
        return _value(self.config["metric"])

    @property
    def transaction_type(self) -> TransactionType | None:
        value = self.config.get("transaction_type")
        return TransactionType(_value(value)) if value is not None else None

    def _where(self, statement):
        return self.source.filter_query(statement, self.config)

    async def _category_items(self, session: AsyncSession) -> list[DatasetItem]:
        assert self.transaction_type is not None
        rows = await rollup_spending_by_top_level_category(
            session,
            transaction_type=self.transaction_type,
            start_date=self.config.get("start_date"),
            end_date=self.config.get("end_date"),
            account_id=self.config.get("account_id"),
        )
        return [
            DatasetItem(
                element_id=row.category_id,
                key=f"category:{row.category_id}",
                name=row.name,
                value=row.amount if self.metric == "sum" else Decimal(row.transaction_count),
                icon=row.icon,
                color=row.color,
            )
            for row in rows
        ]

    async def _subcategory_items(self, session: AsyncSession) -> list[DatasetItem]:
        assert self.transaction_type is not None
        contributions = await raw_category_contributions(
            session,
            transaction_type=self.transaction_type,
            start_date=self.config.get("start_date"),
            end_date=self.config.get("end_date"),
            account_id=self.config.get("account_id"),
        )
        if not contributions:
            return []

        categories_by_id = {c.id: c for c in (await session.execute(select(Category))).scalars().all()}
        amount_by_category: dict[int, Decimal] = defaultdict(Decimal)
        transaction_ids_by_category: dict[int, set[int]] = defaultdict(set)
        for transaction_id, category_id, amount in contributions:
            amount_by_category[category_id] += amount
            transaction_ids_by_category[category_id].add(transaction_id)

        items: list[DatasetItem] = []
        for category_id, amount in amount_by_category.items():
            category = categories_by_id.get(category_id)
            items.append(
                DatasetItem(
                    element_id=category_id,
                    key=f"category:{category_id}",
                    name=category.name if category else "?",
                    value=amount if self.metric == "sum" else Decimal(len(transaction_ids_by_category[category_id])),
                    icon=category.icon if category else None,
                    color=category.color if category else "#898781",
                )
            )
        return items

    async def _account_items(self, session: AsyncSession) -> list[DatasetItem]:
        statement = (
            select(Account.id, Account.name, Account.color, _metric_column(self.metric))
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .group_by(Account.id, Account.name, Account.color)
        )
        statement = self._where(statement)
        rows = (await session.execute(statement)).all()
        return [
            DatasetItem(element_id=account_id, key=f"account:{account_id}", name=name, value=_decimal(value), color=color)
            for account_id, name, color, value in rows
        ]

    async def _tag_items(self, session: AsyncSession) -> list[DatasetItem]:
        statement = (
            select(Tag.id, Tag.name, _metric_column(self.metric))
            .select_from(Transaction)
            .join(transaction_tags, transaction_tags.c.transaction_id == Transaction.id)
            .join(Tag, Tag.id == transaction_tags.c.tag_id)
            .group_by(Tag.id, Tag.name)
        )
        statement = self._where(statement)
        rows = (await session.execute(statement)).all()
        return [
            DatasetItem(element_id=tag_id, key=f"tag:{tag_id}", name=name, value=_decimal(value))
            for tag_id, name, value in rows
        ]

    async def _type_items(self, session: AsyncSession) -> list[DatasetItem]:
        statement = select(Transaction.type, _metric_column(self.metric)).group_by(Transaction.type)
        statement = self._where(statement)
        rows = (await session.execute(statement)).all()
        colors = {"income": "#3aa76d", "expense": "#d6564a", "transfer": "#898781"}
        return [
            DatasetItem(
                element_id=transaction_type.value,
                key=f"transaction_type:{transaction_type.value}",
                name=transaction_type.value,
                value=_decimal(value),
                color=colors.get(transaction_type.value),
            )
            for transaction_type, value in rows
        ]

    async def _total_items(self, session: AsyncSession) -> list[DatasetItem]:
        granularity = _value(self.config["granularity"])
        bucket = func.date_trunc(granularity, Transaction.date)
        statement = (
            select(bucket.label("bucket"), _metric_column(self.metric))
            .group_by("bucket")
            .order_by("bucket")
        )
        statement = self._where(statement)
        rows = (await session.execute(statement)).all()
        return [
            DatasetItem(
                element_id=None,
                key=f"total:{_date_value(bucket_value).isoformat()}",
                name="Total",
                value=_decimal(value),
                time_bucket=_date_value(bucket_value),
                series_key="total",
            )
            for bucket_value, value in rows
        ]

    async def fetch(self, session: AsyncSession) -> Dataset:
        if self.dimension == "category":
            items = await self._category_items(session)
        elif self.dimension == "subcategory":
            items = await self._subcategory_items(session)
        elif self.dimension == "account":
            items = await self._account_items(session)
        elif self.dimension == "tag":
            items = await self._tag_items(session)
        elif self.dimension == "type":
            items = await self._type_items(session)
        else:
            items = await self._total_items(session)
        return Dataset(items=items, kind=self.result_kind(self.dimension))


class TransactionDataSource(DataSource):
    id = "transactions"
    spec_classes: dict[str, type[DataSpec]] = {TransactionAnalyticsDataSpec.id: TransactionAnalyticsDataSpec}

    @staticmethod
    def filter_query(statement, config: Mapping[str, Any]):
        """Shared transaction constraints, always applied before aggregation."""
        if config.get("transaction_type") is not None:
            statement = statement.where(Transaction.type == TransactionType(_value(config["transaction_type"])))
        if config.get("start_date") is not None:
            statement = statement.where(Transaction.date >= config["start_date"])
        if config.get("end_date") is not None:
            statement = statement.where(Transaction.date <= config["end_date"])
        if config.get("account_id") is not None:
            statement = statement.where(Transaction.account_id == config["account_id"])
        return statement

    async def validate_references(self, session: AsyncSession, config: Mapping[str, Any]) -> None:
        account_id = config.get("account_id")
        if account_id is not None and await session.get(Account, account_id) is None:
            raise ValueError("Account not found")


DATA_SOURCE_REGISTRY: dict[str, DataSource] = {}
DATA_SPEC_REGISTRY: dict[tuple[str, str], type[DataSpec]] = {}


def register_data_source(source: DataSource) -> None:
    if not source.id:
        raise ValueError("A data source requires a non-empty id")
    if source.id in DATA_SOURCE_REGISTRY:
        raise ValueError(f"Data source '{source.id}' is already registered")
    for spec in source.list_specs():
        if not spec.id:
            raise ValueError(f"Data source '{source.id}' contains a spec without an id")
        if source.spec_classes.get(spec.id) is not spec:
            raise ValueError(f"Data spec registry key must match '{spec.id}'")
        if (source.id, spec.id) in DATA_SPEC_REGISTRY:
            raise ValueError(f"Data spec '{source.id}:{spec.id}' is already registered")
    DATA_SOURCE_REGISTRY[source.id] = source
    for spec in source.list_specs():
        DATA_SPEC_REGISTRY[(source.id, spec.id)] = spec


def register_data_spec(source_id: str, spec_cls: type[DataSpec]) -> None:
    source = get_data_source(source_id)
    if not spec_cls.id:
        raise ValueError("A data spec requires a non-empty id")
    if spec_cls.id in source.spec_classes:
        raise ValueError(f"Data spec '{source_id}:{spec_cls.id}' is already registered")
    source.spec_classes[spec_cls.id] = spec_cls
    DATA_SPEC_REGISTRY[(source_id, spec_cls.id)] = spec_cls


def get_data_source(source_id: str) -> DataSource:
    try:
        return DATA_SOURCE_REGISTRY[source_id]
    except KeyError as exc:
        raise ValueError(f"Unknown data source '{source_id}'") from exc


register_data_source(TransactionDataSource())
