from datetime import date as date_
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TransactionType, WidgetDimension, WidgetGranularity, WidgetMetric, WidgetType
from app.services.dataset import DatasetKind


class DiagramPointRead(BaseModel):
    label: str
    value: Decimal
    color: str | None = None
    element_id: str | int | None = None
    key: str
    icon: str | None = None
    time_bucket: date_ | None = None
    series_key: str | None = None


class DiagramDataRead(BaseModel):
    points: list[DiagramPointRead]


class DataSpecManifestEntry(BaseModel):
    id: str
    dimensions: list[str]
    metrics: list[str]
    filters: list[str]
    required_parameters: list[str]
    dimension_kinds: dict[str, DatasetKind]
    required_by_dimension: dict[str, list[str]]
    forbidden_by_dimension: dict[str, list[str]]
    filter_options: dict[str, list[str]]
    compatible_diagrams: list[WidgetType]


class DataSourceManifestEntry(BaseModel):
    id: str
    specifications: list[DataSpecManifestEntry]


class WidgetTypeManifestEntry(BaseModel):
    """Backend-declared visualization capabilities and source compatibility."""

    type: WidgetType
    dataset_kind: DatasetKind
    allowed_dimensions: list[str]
    allowed_metrics: list[str]
    needs_granularity: bool
    compatible_data_specs: list[str]


class DashboardWidgetManifest(BaseModel):
    data_sources: list[DataSourceManifestEntry]
    diagrams: list[WidgetTypeManifestEntry]


class DashboardWidgetFields(BaseModel):
    # Defaults preserve the stored/API shape of widgets created before the
    # source/spec split was introduced.
    data_source: str = Field(default="transactions", min_length=1, max_length=50)
    data_spec: str = Field(default="analytics", min_length=1, max_length=80)
    type: WidgetType
    title: str = Field(min_length=1, max_length=100)
    dimension: WidgetDimension
    metric: WidgetMetric
    transaction_type: TransactionType | None = None
    granularity: WidgetGranularity | None = None
    account_id: int | None = None


class DashboardWidgetCreate(DashboardWidgetFields):
    model_config = ConfigDict(extra="forbid")


class DashboardWidgetRead(DashboardWidgetFields):
    """Built explicitly in the service (not via model_validate on the ORM
    row) — `data` isn't a column, it's the Diagram's freshly computed output,
    joined on at read time."""

    id: int
    sort_order: int
    data: DiagramDataRead
