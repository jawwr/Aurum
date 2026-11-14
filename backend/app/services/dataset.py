"""Source-neutral tabular data returned by dashboard data specifications.

The objects in this module deliberately do not import ORM models, transaction
concepts, or chart classes.  A data source may attach whatever identity and
presentation metadata it owns to an item; diagrams consume the same shape
regardless of where the item came from.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal


DatasetKind = Literal["categorical", "time_series"]


@dataclass(frozen=True)
class DatasetItem:
    """One aggregated value in a :class:`Dataset`.

    ``element_id`` is optional because a derived aggregate such as ``Other``
    or a total does not represent one persisted source entity.  ``key`` is
    always required and is stable within the result, making it suitable for
    grouping, reconciliation, and future multi-series charts.
    """

    element_id: str | int | None
    key: str
    name: str
    value: Decimal
    icon: str | None = None
    color: str | None = None
    time_bucket: date | None = None
    series_key: str | None = None

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("A dataset item requires a stable key")
        if isinstance(self.value, bool):
            raise ValueError("A dataset value must be numeric")
        if not isinstance(self.value, Decimal):
            object.__setattr__(self, "value", Decimal(str(self.value)))
        if not self.value.is_finite():
            raise ValueError("A dataset value must be a finite Decimal")


@dataclass
class Dataset:
    """A collection of source-neutral aggregated items."""

    items: list[DatasetItem] = field(default_factory=list)
    kind: DatasetKind = "categorical"

    def __post_init__(self) -> None:
        if self.kind not in {"categorical", "time_series"}:
            raise ValueError("Unsupported dataset kind")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("Dataset item keys must be unique")
        if self.kind == "time_series":
            if any(item.time_bucket is None or not item.series_key for item in self.items):
                raise ValueError("Time-series items require a bucket and series key")
        elif any(item.time_bucket is not None for item in self.items):
            raise ValueError("Categorical items cannot have time buckets")
