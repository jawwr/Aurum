from datetime import date as date_
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    type: WidgetType
    dataset_kind: DatasetKind
    allowed_dimensions: list[str]
    allowed_metrics: list[str]
    needs_granularity: bool
    compatible_data_specs: list[str]


class DashboardWidgetManifest(BaseModel):
    data_sources: list[DataSourceManifestEntry]
    diagrams: list[WidgetTypeManifestEntry]


class WidgetQueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_type: TransactionType | None = None
    account_id: int | None = None


class WidgetQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: WidgetDimension
    metric: WidgetMetric
    filters: WidgetQueryFilters = Field(default_factory=WidgetQueryFilters)
    granularity: WidgetGranularity | None = None


class WidgetVisualization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: WidgetType
    options: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=20)


class DashboardWidgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    data_source: str = Field(min_length=1, max_length=50)
    data_spec: str = Field(min_length=1, max_length=80)
    query: WidgetQuery
    visualization: WidgetVisualization

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value.strip()


class DashboardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Annotated[int, Field(ge=1)]
    widgets: list[DashboardWidgetConfig] = Field(max_length=100)

    @field_validator("schema_version")
    @classmethod
    def supported_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported dashboard schema_version")
        return value

    @model_validator(mode="after")
    def ids_must_be_unique(self):
        ids = [widget.id for widget in self.widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("widget ids must be unique")
        return self


class DashboardWidgetDataRead(BaseModel):
    id: str
    data: DiagramDataRead


class DashboardWidgetsResponse(BaseModel):
    config: DashboardConfig
    widgets: list[DashboardWidgetDataRead]
