"""Source-neutral visualization of an already aggregated Dataset.

No query, financial filter, source identifier, dimension, or metric belongs
here. Compatibility is determined by the shape of the dataset, not its origin.
"""
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.models.enums import WidgetType
from app.services.dataset import Dataset, DatasetItem, DatasetKind


MAX_PIE_SLICES = 8
OTHER_SLICE_COLOR = "#898781"


@dataclass(frozen=True)
class DiagramPoint:
    label: str
    value: Decimal
    key: str
    color: str | None = None
    element_id: str | int | None = None
    icon: str | None = None
    time_bucket: date | None = None
    series_key: str | None = None


@dataclass
class DiagramData:
    points: list[DiagramPoint] = field(default_factory=list)


class Diagram(ABC):
    type: WidgetType
    dataset_kind: DatasetKind
    # Most categorical diagrams can render every categorical dimension, but
    # raw transaction rows are a list/feed rather than a meaningful pie or
    # bar breakdown.
    forbidden_dimensions: tuple[str, ...] = ()

    @classmethod
    def from_options(cls, options: Mapping[str, Any] | None = None) -> "Diagram":
        """Build a diagram from a widget's persisted visualization options.

        Diagrams without options of their own (Pie/Bar/Line) keep accepting
        and ignoring whatever is stored, exactly as before — only
        option-aware diagrams like ListDiagram override this to validate.
        """
        return cls()

    def validate_dataset(self, dataset: Dataset) -> None:
        if dataset.kind != self.dataset_kind:
            raise ValueError(f"A {self.type.value} diagram requires a {self.dataset_kind} dataset")

    @staticmethod
    def _point(item: DatasetItem) -> DiagramPoint:
        return DiagramPoint(
            label=item.time_bucket.isoformat() if item.time_bucket is not None else item.name,
            value=item.value,
            color=item.color,
            element_id=item.element_id,
            key=item.key,
            icon=item.icon,
            time_bucket=item.time_bucket,
            series_key=item.series_key,
        )

    @abstractmethod
    def render(self, dataset: Dataset) -> DiagramData:
        """Transform an already-fetched dataset into chart data."""


class PieDiagram(Diagram):
    type = WidgetType.PIE
    dataset_kind = "categorical"
    forbidden_dimensions = ("item",)

    def render(self, dataset: Dataset) -> DiagramData:
        self.validate_dataset(dataset)
        points = sorted((self._point(item) for item in dataset.items), key=lambda point: -point.value)
        top, rest = points[:MAX_PIE_SLICES], points[MAX_PIE_SLICES:]
        if rest:
            top.append(
                DiagramPoint(
                    label="Other",
                    value=sum((point.value for point in rest), Decimal("0")),
                    color=OTHER_SLICE_COLOR,
                    element_id=None,
                    key="diagram:other",
                )
            )
        return DiagramData(points=top)


class BarDiagram(Diagram):
    type = WidgetType.BAR
    dataset_kind = "categorical"
    forbidden_dimensions = ("item",)

    def render(self, dataset: Dataset) -> DiagramData:
        self.validate_dataset(dataset)
        return DiagramData(points=sorted((self._point(item) for item in dataset.items), key=lambda point: -point.value))


class LineDiagram(Diagram):
    """The current renderer supports one time series and leaves gaps unfilled."""

    type = WidgetType.LINE
    dataset_kind = "time_series"

    def render(self, dataset: Dataset) -> DiagramData:
        self.validate_dataset(dataset)
        if any(item.time_bucket is None for item in dataset.items):
            raise ValueError("A line dataset requires time buckets")
        if len({item.series_key for item in dataset.items}) > 1:
            raise ValueError("The current line diagram supports a single series")
        points = [self._point(item) for item in dataset.items]
        points.sort(key=lambda point: point.time_bucket or date.min)
        return DiagramData(points=points)


class ListDiagram(Diagram):
    """A vertical analytical list: one row per aggregated group.

    Sorting is deliberately explicit — ``none`` keeps the DataSource's own
    order (no hidden value or alphabetical sort), ``value_asc`` and
    ``value_desc`` sort by the signed numeric value. Thus ``value_desc`` puts
    ``100000`` before ``-30000``, while ``value_asc`` puts ``-30000`` first.
    The limit is applied after any sorting, never before.
    """

    type = WidgetType.LIST
    dataset_kind = "categorical"

    SORTS = ("none", "value_asc", "value_desc")
    DEFAULT_SORT = "none"
    DEFAULT_LIMIT = 5

    def __init__(self, *, sort: str = DEFAULT_SORT, limit: int = DEFAULT_LIMIT) -> None:
        if sort not in self.SORTS:
            raise ValueError(f"Unsupported list sort '{sort}'")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("A list widget limit must be a positive integer")
        self.sort = sort
        self.limit = limit

    @classmethod
    def from_options(cls, options: Mapping[str, Any] | None = None) -> "ListDiagram":
        unsupported = sorted(set(options or {}) - {"sort", "limit"})
        if unsupported:
            raise ValueError(f"A list diagram does not support the '{unsupported[0]}' option")
        sort = (options or {}).get("sort")
        limit = (options or {}).get("limit")
        return cls(
            sort=cls.DEFAULT_SORT if sort is None else sort,
            limit=cls.DEFAULT_LIMIT if limit is None else limit,
        )

    def render(self, dataset: Dataset) -> DiagramData:
        self.validate_dataset(dataset)
        points = [self._point(item) for item in dataset.items]
        if self.sort == "value_asc":
            points.sort(key=lambda point: point.value)
        elif self.sort == "value_desc":
            points.sort(key=lambda point: point.value, reverse=True)
        return DiagramData(points=points[: self.limit])


DIAGRAM_REGISTRY: dict[WidgetType, type[Diagram]] = {
    WidgetType.PIE: PieDiagram,
    WidgetType.BAR: BarDiagram,
    WidgetType.LINE: LineDiagram,
    WidgetType.LIST: ListDiagram,
}
