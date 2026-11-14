"""A user-added Dashboard chart — the fixed "Spending by category"/"Income by
category" donuts stay hardcoded on the page and never go through this table;
this is only for widgets added via the "Add widget" constructor. See
services/diagrams.py for how a row here turns into actual chart data."""
from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TransactionType, WidgetDimension, WidgetGranularity, WidgetMetric, WidgetType
from app.models.mixins import TimestampMixin


class DashboardWidget(Base, TimestampMixin):
    __tablename__ = "dashboard_widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[WidgetType] = mapped_column(
        Enum(WidgetType, name="dashboard_widget_type", native_enum=False, length=10), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[WidgetDimension] = mapped_column(
        Enum(WidgetDimension, name="dashboard_widget_dimension", native_enum=False, length=20), nullable=False
    )
    metric: Mapped[WidgetMetric] = mapped_column(
        Enum(WidgetMetric, name="dashboard_widget_metric", native_enum=False, length=10), nullable=False
    )
    # Required for every dimension except TOTAL — see services/diagrams.py's
    # Diagram._validate. Summing income+expense+transfer together in one bar
    # is meaningless, so a widget is always scoped to one transaction type
    # unless it's explicitly breaking totals down *by* type.
    transaction_type: Mapped[TransactionType | None] = mapped_column(
        Enum(TransactionType, name="dashboard_widget_transaction_type", native_enum=False, length=10), nullable=True
    )
    # Only meaningful (and required) for type=LINE.
    granularity: Mapped[WidgetGranularity | None] = mapped_column(
        Enum(WidgetGranularity, name="dashboard_widget_granularity", native_enum=False, length=20), nullable=True
    )
    # Optional extra filter, on top of dimension/transaction_type — "just
    # this account's category breakdown". SET NULL so deleting an account
    # doesn't take the widget down with it, only drops that one filter.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    # Display order in the "Add widget" grid — assigned as max(sort_order)+1
    # at creation time (see services/dashboard_widget_service.py).
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    account: Mapped["Account | None"] = relationship()
