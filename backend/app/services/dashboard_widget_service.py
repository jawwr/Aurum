"""CRUD for user-added Dashboard widgets.

Widget configuration is persisted, while numbers are recomputed for the
selected month.  Data acquisition is delegated to a registered DataSource /
DataSpec pair and the resulting Dataset is passed to a source-neutral Diagram.
"""
import calendar
from datetime import date as date_

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_widget import DashboardWidget
from app.models.enums import WidgetType
from app.schemas.dashboard_widget import (
    DashboardWidgetCreate,
    DashboardWidgetManifest,
    DashboardWidgetRead,
    DataSourceManifestEntry,
    DataSpecManifestEntry,
    DiagramDataRead,
    DiagramPointRead,
    WidgetTypeManifestEntry,
)
from app.services.data_sources import DATA_SOURCE_REGISTRY, DataSpec, get_data_source
from app.services.diagrams import DIAGRAM_REGISTRY, Diagram


def _spec_key(source_id: str, spec_id: str) -> str:
    return f"{source_id}:{spec_id}"


def _compatible_dimensions(spec_cls: type[DataSpec], diagram_cls: type[Diagram]) -> list[str]:
    return [
        dimension
        for dimension in spec_cls.dimensions
        if spec_cls.result_kind(dimension) == diagram_cls.dataset_kind
    ]


def list_widget_types() -> DashboardWidgetManifest:
    """Return the complete backend capability manifest.

    The frontend may still hide source/spec selectors while there is only one
    source and one spec, but it receives the actual capabilities from this
    endpoint rather than maintaining a parallel list.
    """
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
                    compatible_diagrams=[
                        diagram_cls.type
                        for diagram_cls in DIAGRAM_REGISTRY.values()
                        if _compatible_dimensions(spec_cls, diagram_cls)
                    ],
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
            allowed_dimensions=list(dict.fromkeys(
                dimension
                for _, spec_cls in compatible_specs
                for dimension in _compatible_dimensions(spec_cls, diagram_cls)
            )),
            allowed_metrics=list(dict.fromkeys(metric for _, spec_cls in compatible_specs for metric in spec_cls.metrics)),
            needs_granularity=any(
                "granularity" in spec_cls.required_by_dimension.get(dimension, ())
                for _, spec_cls in compatible_specs
                for dimension in _compatible_dimensions(spec_cls, diagram_cls)
            ),
            compatible_data_specs=[_spec_key(source_id, spec_cls.id) for source_id, spec_cls in compatible_specs],
        ))
    return DashboardWidgetManifest(data_sources=data_sources, diagrams=diagrams)


def _month_bounds(year: int, month: int) -> tuple[date_, date_]:
    last_day = calendar.monthrange(year, month)[1]
    return date_(year, month, 1), date_(year, month, last_day)


def _fields_config(
    fields: DashboardWidgetCreate | DashboardWidget,
    *,
    start: date_ | None,
    end: date_ | None,
) -> dict:
    return {
        "dimension": fields.dimension,
        "metric": fields.metric,
        "transaction_type": fields.transaction_type,
        "granularity": fields.granularity,
        "account_id": fields.account_id,
        "start_date": start,
        "end_date": end,
    }


def _build_diagram(widget_type: WidgetType) -> Diagram:
    diagram_cls = DIAGRAM_REGISTRY.get(widget_type)
    if diagram_cls is None:
        raise ValueError(f"Unsupported diagram type '{widget_type.value}'")
    return diagram_cls()


def _build_spec(fields: DashboardWidgetCreate | DashboardWidget, start: date_ | None, end: date_ | None) -> DataSpec:
    source = get_data_source(fields.data_source)
    return source.create_spec(fields.data_spec, config=_fields_config(fields, start=start, end=end))


def _validate_compatibility(diagram: Diagram, spec: DataSpec) -> None:
    if spec.result_kind(spec.config["dimension"]) != diagram.dataset_kind:
        raise ValueError(f"Data spec dimension is not compatible with a {diagram.type.value} widget")


def _validate_widget_config(payload: DashboardWidgetCreate) -> DataSpec:
    try:
        spec = _build_spec(payload, start=None, end=None)
        _validate_compatibility(_build_diagram(payload.type), spec)
        return spec
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _to_read(session: AsyncSession, widget: DashboardWidget, start: date_, end: date_) -> DashboardWidgetRead:
    try:
        diagram = _build_diagram(widget.type)
        spec = _build_spec(widget, start=start, end=end)
        _validate_compatibility(diagram, spec)
        data = diagram.render(await spec.fetch(session))
    except ValueError as exc:
        # Existing rows are validated on write, but this also gives a stable
        # API error if a future migration encounters an unrepresentable row.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DashboardWidgetRead(
        id=widget.id,
        data_source=widget.data_source,
        data_spec=widget.data_spec,
        type=widget.type,
        title=widget.title,
        dimension=widget.dimension,
        metric=widget.metric,
        transaction_type=widget.transaction_type,
        granularity=widget.granularity,
        account_id=widget.account_id,
        sort_order=widget.sort_order,
        data=DiagramDataRead(
            points=[
                DiagramPointRead(
                    label=point.label,
                    value=point.value,
                    color=point.color,
                    element_id=point.element_id,
                    key=point.key,
                    icon=point.icon,
                    time_bucket=point.time_bucket,
                    series_key=point.series_key,
                )
                for point in data.points
            ]
        ),
    )


async def list_widgets(session: AsyncSession, year: int, month: int) -> list[DashboardWidgetRead]:
    start, end = _month_bounds(year, month)
    rows = (
        (await session.execute(select(DashboardWidget).order_by(DashboardWidget.sort_order, DashboardWidget.id)))
        .scalars()
        .all()
    )
    return [await _to_read(session, widget, start, end) for widget in rows]


async def _validate_and_check_references(session: AsyncSession, payload: DashboardWidgetCreate) -> None:
    spec = _validate_widget_config(payload)
    try:
        await spec.validate_references(session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _apply_fields(widget: DashboardWidget, payload: DashboardWidgetCreate) -> None:
    widget.data_source = payload.data_source
    widget.data_spec = payload.data_spec
    widget.type = payload.type
    widget.title = payload.title
    widget.dimension = payload.dimension
    widget.metric = payload.metric
    widget.transaction_type = payload.transaction_type
    widget.granularity = payload.granularity
    widget.account_id = payload.account_id


async def create_widget(session: AsyncSession, payload: DashboardWidgetCreate, year: int, month: int) -> DashboardWidgetRead:
    await _validate_and_check_references(session, payload)

    max_sort_order = (await session.execute(select(func.max(DashboardWidget.sort_order)))).scalar_one()
    widget = DashboardWidget(sort_order=(max_sort_order or 0) + 1)
    _apply_fields(widget, payload)
    session.add(widget)
    await session.commit()
    await session.refresh(widget)

    start, end = _month_bounds(year, month)
    return await _to_read(session, widget, start, end)


async def update_widget(
    session: AsyncSession, widget_id: int, payload: DashboardWidgetCreate, year: int, month: int
) -> DashboardWidgetRead:
    widget = await session.get(DashboardWidget, widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    await _validate_and_check_references(session, payload)

    _apply_fields(widget, payload)
    await session.commit()
    await session.refresh(widget)

    start, end = _month_bounds(year, month)
    return await _to_read(session, widget, start, end)


async def delete_widget(session: AsyncSession, widget_id: int) -> None:
    widget = await session.get(DashboardWidget, widget_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    await session.delete(widget)
    await session.commit()
