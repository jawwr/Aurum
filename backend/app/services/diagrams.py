"""Source-neutral visualization of an already aggregated Dataset.

No query, financial filter, source identifier, dimension, or metric belongs
here. Compatibility is determined by the shape of the dataset, not its origin.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

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


DIAGRAM_REGISTRY: dict[WidgetType, type[Diagram]] = {
    WidgetType.PIE: PieDiagram,
    WidgetType.BAR: BarDiagram,
    WidgetType.LINE: LineDiagram,
}
