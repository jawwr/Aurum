"""One class per dashboard widget chart shape — Pie/Bar/Line — each declaring
which dimension/metric combinations it accepts and how to turn a
(dimension, metric, period, filters) config into chart-ready points.

The shared base (Diagram) validates that combination and dispatches to one of
five dimension resolvers below. CATEGORY and SUBCATEGORY both fold in
split-transaction lines the same way the Dashboard's fixed "Spending by
category" donut does, but differ in rollup: CATEGORY merges a subcategory's
amount into its parent (one point per top-level category), SUBCATEGORY keeps
every category at its own leaf level (a point per subcategory, and per
top-level category that has no children or was itself the direct pick).
ACCOUNT, TAG and TYPE are plain single-table group-bys with no such rollup.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.enums import TransactionType, WidgetDimension, WidgetGranularity, WidgetMetric, WidgetType
from app.models.tag import Tag, transaction_tags
from app.models.transaction import Transaction
from app.services.category_rollup import raw_category_contributions, rollup_spending_by_top_level_category

# Same cap/color as the Dashboard's fixed category donuts (dashboard_service.py)
# — a widget with more slices than this collapses the tail into "Other"
# rather than fanning out into an unreadable chart.
MAX_PIE_SLICES = 8
OTHER_SLICE_COLOR = "#898781"

_TYPE_LABELS = {
    TransactionType.INCOME: "income",
    TransactionType.EXPENSE: "expense",
    TransactionType.TRANSFER: "transfer",
}
_TYPE_COLORS = {
    TransactionType.INCOME: "#3aa76d",
    TransactionType.EXPENSE: "#d6564a",
    TransactionType.TRANSFER: "#898781",
}


@dataclass
class DiagramPoint:
    label: str
    value: Decimal
    color: str | None = None


@dataclass
class DiagramData:
    points: list[DiagramPoint] = field(default_factory=list)


def _metric_column(metric: WidgetMetric):
    return func.sum(Transaction.amount) if metric == WidgetMetric.SUM else func.count(Transaction.id)


async def _points_for_category(
    session: AsyncSession, *, transaction_type: TransactionType, metric: WidgetMetric, start: date_ | None, end: date_ | None,
    account_id: int | None,
) -> list[DiagramPoint]:
    rows = await rollup_spending_by_top_level_category(
        session, transaction_type=transaction_type, start_date=start, end_date=end, account_id=account_id
    )
    return [
        DiagramPoint(
            label=row.name,
            value=row.amount if metric == WidgetMetric.SUM else Decimal(row.transaction_count),
            color=row.color,
        )
        for row in rows
    ]


async def _points_for_subcategory(
    session: AsyncSession, *, transaction_type: TransactionType, metric: WidgetMetric, start: date_ | None, end: date_ | None,
    account_id: int | None,
) -> list[DiagramPoint]:
    contributions = await raw_category_contributions(
        session, transaction_type=transaction_type, start_date=start, end_date=end, account_id=account_id
    )
    if not contributions:
        return []

    categories_by_id = {c.id: c for c in (await session.execute(select(Category))).scalars().all()}
    amount_by_category: dict[int, Decimal] = defaultdict(Decimal)
    transaction_ids_by_category: dict[int, set[int]] = defaultdict(set)
    for transaction_id, category_id, amount in contributions:
        amount_by_category[category_id] += amount
        transaction_ids_by_category[category_id].add(transaction_id)

    points: list[DiagramPoint] = []
    for category_id, amount in amount_by_category.items():
        category = categories_by_id.get(category_id)
        value = amount if metric == WidgetMetric.SUM else Decimal(len(transaction_ids_by_category[category_id]))
        points.append(
            DiagramPoint(
                label=category.name if category else "?",
                value=value,
                color=category.color if category else OTHER_SLICE_COLOR,
            )
        )
    return points


async def _points_for_account(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    metric: WidgetMetric,
    start: date_ | None,
    end: date_ | None,
    account_id: int | None,
) -> list[DiagramPoint]:
    stmt = (
        select(Account.name, Account.color, _metric_column(metric))
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.type == transaction_type)
        .group_by(Account.id, Account.name, Account.color)
    )
    if start is not None:
        stmt = stmt.where(Transaction.date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.date <= end)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    rows = (await session.execute(stmt)).all()
    return [DiagramPoint(label=name, value=Decimal(value), color=color) for name, color, value in rows]


async def _points_for_tag(
    session: AsyncSession,
    *,
    transaction_type: TransactionType,
    metric: WidgetMetric,
    start: date_ | None,
    end: date_ | None,
    account_id: int | None,
) -> list[DiagramPoint]:
    # Tag has no color of its own (unlike Category/Account) — the frontend
    # falls back to its own categorical palette for these points.
    stmt = (
        select(Tag.name, _metric_column(metric))
        .select_from(Transaction)
        .join(transaction_tags, transaction_tags.c.transaction_id == Transaction.id)
        .join(Tag, Tag.id == transaction_tags.c.tag_id)
        .where(Transaction.type == transaction_type)
        .group_by(Tag.id, Tag.name)
    )
    if start is not None:
        stmt = stmt.where(Transaction.date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.date <= end)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    rows = (await session.execute(stmt)).all()
    return [DiagramPoint(label=name, value=Decimal(value)) for name, value in rows]


async def _points_for_type(
    session: AsyncSession, *, metric: WidgetMetric, start: date_ | None, end: date_ | None, account_id: int | None
) -> list[DiagramPoint]:
    stmt = select(Transaction.type, _metric_column(metric)).group_by(Transaction.type)
    if start is not None:
        stmt = stmt.where(Transaction.date >= start)
    if end is not None:
        stmt = stmt.where(Transaction.date <= end)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    rows = (await session.execute(stmt)).all()
    return [
        DiagramPoint(label=_TYPE_LABELS[tx_type], value=Decimal(value), color=_TYPE_COLORS.get(tx_type))
        for tx_type, value in rows
    ]


class Diagram(ABC):
    """Base for a configurable dashboard widget. Subclasses only differ in
    `allowed_dimensions`/`allowed_metrics` and how they post-process the raw
    (dimension, metric) breakdown in `fetch` — Pie collapses a long tail into
    "Other", Bar doesn't, Line ignores the breakdown entirely and buckets by
    time instead."""

    type: WidgetType
    allowed_dimensions: list[WidgetDimension]
    allowed_metrics: list[WidgetMetric]

    def __init__(
        self,
        *,
        dimension: WidgetDimension,
        metric: WidgetMetric,
        transaction_type: TransactionType | None,
        granularity: WidgetGranularity | None,
        account_id: int | None,
        start: date_ | None,
        end: date_ | None,
    ) -> None:
        self.dimension = dimension
        self.metric = metric
        self.transaction_type = transaction_type
        self.granularity = granularity
        self.account_id = account_id
        self.start = start
        self.end = end
        self._validate()

    def _validate(self) -> None:
        if self.dimension not in self.allowed_dimensions:
            raise ValueError(f"'{self.dimension.value}' is not a valid dimension for a {self.type.value} widget")
        if self.metric not in self.allowed_metrics:
            raise ValueError(f"'{self.metric.value}' is not a valid metric for a {self.type.value} widget")
        # A widget broken down *by* type can't also be filtered to one type
        # (there'd be nothing left to break down) — every other dimension
        # needs a type, or summing income+expense+transfer together would be
        # a meaningless total.
        if self.dimension == WidgetDimension.TYPE and self.transaction_type is not None:
            raise ValueError("transaction_type must be omitted when dimension is 'type'")
        if self.dimension != WidgetDimension.TYPE and self.transaction_type is None:
            raise ValueError("transaction_type is required for this dimension")
        if self.type == WidgetType.LINE and self.granularity is None:
            raise ValueError("granularity is required for a line widget")
        if self.type != WidgetType.LINE and self.granularity is not None:
            raise ValueError("granularity is only valid for a line widget")

    async def _raw_points(self, session: AsyncSession) -> list[DiagramPoint]:
        if self.dimension == WidgetDimension.CATEGORY:
            assert self.transaction_type is not None
            return await _points_for_category(
                session, transaction_type=self.transaction_type, metric=self.metric, start=self.start, end=self.end,
                account_id=self.account_id,
            )
        if self.dimension == WidgetDimension.SUBCATEGORY:
            assert self.transaction_type is not None
            return await _points_for_subcategory(
                session, transaction_type=self.transaction_type, metric=self.metric, start=self.start, end=self.end,
                account_id=self.account_id,
            )
        if self.dimension == WidgetDimension.ACCOUNT:
            assert self.transaction_type is not None
            return await _points_for_account(
                session,
                transaction_type=self.transaction_type,
                metric=self.metric,
                start=self.start,
                end=self.end,
                account_id=self.account_id,
            )
        if self.dimension == WidgetDimension.TAG:
            assert self.transaction_type is not None
            return await _points_for_tag(
                session,
                transaction_type=self.transaction_type,
                metric=self.metric,
                start=self.start,
                end=self.end,
                account_id=self.account_id,
            )
        return await _points_for_type(session, metric=self.metric, start=self.start, end=self.end, account_id=self.account_id)

    @abstractmethod
    async def fetch(self, session: AsyncSession) -> DiagramData: ...


class PieDiagram(Diagram):
    type = WidgetType.PIE
    allowed_dimensions = [
        WidgetDimension.CATEGORY,
        WidgetDimension.SUBCATEGORY,
        WidgetDimension.ACCOUNT,
        WidgetDimension.TAG,
        WidgetDimension.TYPE,
    ]
    allowed_metrics = [WidgetMetric.SUM, WidgetMetric.COUNT]

    async def fetch(self, session: AsyncSession) -> DiagramData:
        points = sorted(await self._raw_points(session), key=lambda p: -p.value)
        top, rest = points[:MAX_PIE_SLICES], points[MAX_PIE_SLICES:]
        if rest:
            other_value = sum((p.value for p in rest), Decimal("0"))
            top.append(DiagramPoint(label="Other", value=other_value, color=OTHER_SLICE_COLOR))
        return DiagramData(points=top)


class BarDiagram(Diagram):
    type = WidgetType.BAR
    allowed_dimensions = [
        WidgetDimension.CATEGORY,
        WidgetDimension.SUBCATEGORY,
        WidgetDimension.ACCOUNT,
        WidgetDimension.TAG,
        WidgetDimension.TYPE,
    ]
    allowed_metrics = [WidgetMetric.SUM, WidgetMetric.COUNT]

    async def fetch(self, session: AsyncSession) -> DiagramData:
        points = sorted(await self._raw_points(session), key=lambda p: -p.value)
        return DiagramData(points=points)


class LineDiagram(Diagram):
    """No dimension breakdown (multi-series line charts aren't supported
    yet) — just one line, the metric bucketed by day/week/month."""

    type = WidgetType.LINE
    allowed_dimensions = [WidgetDimension.TOTAL]
    allowed_metrics = [WidgetMetric.SUM, WidgetMetric.COUNT]

    async def fetch(self, session: AsyncSession) -> DiagramData:
        assert self.granularity is not None and self.transaction_type is not None
        bucket = func.date_trunc(self.granularity.value, Transaction.date)
        stmt = (
            select(bucket.label("bucket"), _metric_column(self.metric))
            .where(Transaction.type == self.transaction_type)
            .group_by("bucket")
            .order_by("bucket")
        )
        if self.start is not None:
            stmt = stmt.where(Transaction.date >= self.start)
        if self.end is not None:
            stmt = stmt.where(Transaction.date <= self.end)
        if self.account_id is not None:
            stmt = stmt.where(Transaction.account_id == self.account_id)
        rows = (await session.execute(stmt)).all()
        # bucket comes back as a datetime (date_trunc's return type) — ISO
        # date string only, the frontend formats it per the widget's own
        # granularity (same split as formatCurrency/formatTransactionDate
        # elsewhere: backend ships raw values, frontend owns display format).
        return DiagramData(
            points=[DiagramPoint(label=bucket_value.date().isoformat(), value=Decimal(value)) for bucket_value, value in rows]
        )


DIAGRAM_REGISTRY: dict[WidgetType, type[Diagram]] = {
    WidgetType.PIE: PieDiagram,
    WidgetType.BAR: BarDiagram,
    WidgetType.LINE: LineDiagram,
}
