"""Dashboard configuration storage and period-specific widget rendering."""
import calendar
from datetime import date as date_

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WidgetType
from app.models.settings import AppSettings
from app.schemas.dashboard_widget import (
    DashboardConfig,
    DashboardWidgetConfig,
    DashboardWidgetDataRead,
    DashboardWidgetManifest,
    DashboardWidgetsResponse,
    DataSourceManifestEntry,
    DataSpecManifestEntry,
    DiagramDataRead,
    DiagramPointRead,
    WidgetTypeManifestEntry,
)
from app.services.data_sources import DATA_SOURCE_REGISTRY, DataSpec, get_data_source
from app.services.diagrams import DIAGRAM_REGISTRY, Diagram
from app.services.settings_service import get_or_create_app_settings


def _spec_key(source_id: str, spec_id: str) -> str:
    return f"{source_id}:{spec_id}"


def _compatible_dimensions(spec_cls: type[DataSpec], diagram_cls: type[Diagram]) -> list[str]:
    return [dimension for dimension in spec_cls.dimensions if spec_cls.result_kind(dimension) == diagram_cls.dataset_kind]


def list_widget_types() -> DashboardWidgetManifest:
    data_sources = [
        DataSourceManifestEntry(
            id=source_id,
            specifications=[
                DataSpecManifestEntry(
                    id=spec_cls.id,
                    dimensions=list(spec_cls.dimensions),
                    metrics=list(spec_cls.metrics),
                    filters=list(spec_cls.supported_filters),
                    required_parameters=list(spec_cls.required_parameters),
                    dimension_kinds=dict(spec_cls.dimension_kinds),
                    required_by_dimension={key: list(value) for key, value in spec_cls.required_by_dimension.items()},
                    forbidden_by_dimension={key: list(value) for key, value in spec_cls.forbidden_by_dimension.items()},
                    filter_options={key: list(value) for key, value in spec_cls.filter_options.items()},
                    compatible_diagrams=[diagram_cls.type for diagram_cls in DIAGRAM_REGISTRY.values() if _compatible_dimensions(spec_cls, diagram_cls)],
                )
                for spec_cls in source.spec_classes.values()
            ],
        )
        for source_id, source in DATA_SOURCE_REGISTRY.items()
    ]
    diagrams = []
    for diagram_cls in DIAGRAM_REGISTRY.values():
        compatible_specs = [
            (source_id, spec_cls)
            for source_id, source in DATA_SOURCE_REGISTRY.items()
            for spec_cls in source.list_specs()
            if _compatible_dimensions(spec_cls, diagram_cls)
        ]
        diagrams.append(WidgetTypeManifestEntry(
            type=diagram_cls.type,
            dataset_kind=diagram_cls.dataset_kind,
            allowed_dimensions=list(dict.fromkeys(dimension for _, spec_cls in compatible_specs for dimension in _compatible_dimensions(spec_cls, diagram_cls))),
            allowed_metrics=list(dict.fromkeys(metric for _, spec_cls in compatible_specs for metric in spec_cls.metrics)),
            needs_granularity=any("granularity" in spec_cls.required_by_dimension.get(dimension, ()) for _, spec_cls in compatible_specs for dimension in _compatible_dimensions(spec_cls, diagram_cls)),
            compatible_data_specs=[_spec_key(source_id, spec_cls.id) for source_id, spec_cls in compatible_specs],
        ))
    return DashboardWidgetManifest(data_sources=data_sources, diagrams=diagrams)


def _month_bounds(year: int, month: int) -> tuple[date_, date_]:
    return date_(year, month, 1), date_(year, month, calendar.monthrange(year, month)[1])


def _fields_config(widget: DashboardWidgetConfig, *, start: date_ | None, end: date_ | None) -> dict:
    return {
        "dimension": widget.query.dimension,
        "metric": widget.query.metric,
        "transaction_type": widget.query.filters.transaction_type,
        "granularity": widget.query.granularity,
        "account_id": widget.query.filters.account_id,
        "start_date": start,
        "end_date": end,
    }


def _build_diagram(widget_type: WidgetType) -> Diagram:
    diagram_cls = DIAGRAM_REGISTRY.get(widget_type)
    if diagram_cls is None:
        raise ValueError(f"Unsupported diagram type '{widget_type.value}'")
    return diagram_cls()


def _build_spec(widget: DashboardWidgetConfig, start: date_ | None, end: date_ | None) -> DataSpec:
    source = get_data_source(widget.data_source)
    return source.create_spec(widget.data_spec, config=_fields_config(widget, start=start, end=end))


def _validate_widget_config(widget: DashboardWidgetConfig) -> DataSpec:
    try:
        spec = _build_spec(widget, start=None, end=None)
        if spec.result_kind(widget.query.dimension) != _build_diagram(widget.visualization.type).dataset_kind:
            raise ValueError(f"Data spec dimension is not compatible with a {widget.visualization.type.value} widget")
        return spec
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _validate_config_references(session: AsyncSession, config: DashboardConfig) -> None:
    for widget in config.widgets:
        spec = _validate_widget_config(widget)
        try:
            await spec.validate_references(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _render_widget(session: AsyncSession, widget: DashboardWidgetConfig, start: date_, end: date_) -> DashboardWidgetDataRead:
    try:
        diagram = _build_diagram(widget.visualization.type)
        data = diagram.render(await _build_spec(widget, start=start, end=end).fetch(session))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DashboardWidgetDataRead(
        id=widget.id,
        data=DiagramDataRead(points=[
            DiagramPointRead(label=point.label, value=point.value, color=point.color, element_id=point.element_id,
                              key=point.key, icon=point.icon, time_bucket=point.time_bucket, series_key=point.series_key)
            for point in data.points
        ]),
    )


async def _response(session: AsyncSession, config: DashboardConfig, year: int, month: int) -> DashboardWidgetsResponse:
    start, end = _month_bounds(year, month)
    return DashboardWidgetsResponse(config=config, widgets=[await _render_widget(session, widget, start, end) for widget in config.widgets])


async def list_widgets(session: AsyncSession, year: int, month: int) -> DashboardWidgetsResponse:
    settings = await get_or_create_app_settings(session)
    try:
        config = DashboardConfig.model_validate(settings.dashboard_config)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Stored Dashboard configuration is invalid") from exc
    return await _response(session, config, year, month)


async def save_widgets(session: AsyncSession, config: DashboardConfig, year: int, month: int) -> DashboardWidgetsResponse:
    await _validate_config_references(session, config)
    settings = await session.get(AppSettings, 1)
    if settings is None:
        settings = AppSettings(id=1)
        session.add(settings)
        await session.flush()
    settings.dashboard_config = config.model_dump(mode="json")
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(settings)
    return await _response(session, DashboardConfig.model_validate(settings.dashboard_config), year, month)
