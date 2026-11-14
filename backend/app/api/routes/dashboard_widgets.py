from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.dashboard_widget import DashboardWidgetCreate, DashboardWidgetRead, WidgetTypeManifestEntry
from app.services.dashboard_widget_service import (
    create_widget,
    delete_widget,
    list_widget_types,
    list_widgets,
    update_widget,
)

router = APIRouter(prefix="/dashboard/widgets", tags=["dashboard-widgets"])


@router.get("/types", response_model=list[WidgetTypeManifestEntry])
def read_widget_types() -> list[WidgetTypeManifestEntry]:
    """Drives the "Add widget" form's dimension/metric pickers straight from
    what the Diagram subclasses actually accept (services/diagrams.py),
    instead of a second hand-kept list on the frontend that could drift."""
    return list_widget_types()


@router.get("", response_model=list[DashboardWidgetRead])
async def read_widgets(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> list[DashboardWidgetRead]:
    return await list_widgets(session, year, month)


@router.post("", response_model=DashboardWidgetRead, status_code=201)
async def add_widget(
    payload: DashboardWidgetCreate,
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> DashboardWidgetRead:
    return await create_widget(session, payload, year, month)


@router.patch("/{widget_id}", response_model=DashboardWidgetRead)
async def edit_widget(
    widget_id: int,
    payload: DashboardWidgetCreate,
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> DashboardWidgetRead:
    return await update_widget(session, widget_id, payload, year, month)


@router.delete("/{widget_id}", status_code=204)
async def remove_widget(widget_id: int, session: AsyncSession = Depends(get_session)) -> None:
    await delete_widget(session, widget_id)
