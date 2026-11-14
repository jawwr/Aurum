from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import TransactionType, WidgetDimension, WidgetGranularity, WidgetMetric, WidgetType


class DiagramPointRead(BaseModel):
    label: str
    value: Decimal
    color: str | None = None


class DiagramDataRead(BaseModel):
    points: list[DiagramPointRead]


class WidgetTypeManifestEntry(BaseModel):
    """One entry per WidgetType, so the "Add widget" form's dimension/metric
    pickers are driven by what the backend's Diagram subclasses actually
    accept (see services/diagrams.py) instead of a second, hand-kept list on
    the frontend that could drift out of sync."""

    type: WidgetType
    allowed_dimensions: list[WidgetDimension]
    allowed_metrics: list[WidgetMetric]
    needs_granularity: bool


class DashboardWidgetFields(BaseModel):
    type: WidgetType
    title: str = Field(min_length=1, max_length=100)
    dimension: WidgetDimension
    metric: WidgetMetric
    transaction_type: TransactionType | None = None
    granularity: WidgetGranularity | None = None
    account_id: int | None = None


class DashboardWidgetCreate(DashboardWidgetFields):
    pass


class DashboardWidgetRead(DashboardWidgetFields):
    """Built explicitly in the service (not via model_validate on the ORM
    row) — `data` isn't a column, it's the Diagram's freshly computed output,
    joined on at read time."""

    id: int
    sort_order: int
    data: DiagramDataRead
