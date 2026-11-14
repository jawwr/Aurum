from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.dashboard_widget import DashboardConfig, DashboardWidgetManifest, DashboardWidgetsResponse
from app.services.dashboard_widget_service import (
    list_widget_types,
    list_widgets,
    save_widgets,
)

router = APIRouter(prefix="/dashboard/widgets", tags=["dashboard-widgets"])


@router.get("/types", response_model=DashboardWidgetManifest)
def read_widget_types() -> DashboardWidgetManifest:
    """Return data-source and diagram capabilities from backend registries."""
    return list_widget_types()


@router.get("", response_model=DashboardWidgetsResponse)
async def read_widgets(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> DashboardWidgetsResponse:
    return await list_widgets(session, year, month)


@router.put("", response_model=DashboardWidgetsResponse)
async def save_dashboard_widgets(
    payload: DashboardConfig,
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    session: AsyncSession = Depends(get_session),
) -> DashboardWidgetsResponse:
    return await save_widgets(session, payload, year, month)
