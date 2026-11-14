"""store the Dashboard as one versioned JSON document

Revision ID: 7c1d2e3f4a56
Revises: d2f7a1b8c904
"""
from typing import Sequence, Union

from alembic import op
import json
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7c1d2e3f4a56"
down_revision: Union[str, None] = "d2f7a1b8c904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column(
        "app_settings",
        sa.Column("dashboard_config", postgresql.JSONB(), nullable=True),
    )

    rows = connection.execute(sa.text("""
        SELECT id, data_source, data_spec, type, title, dimension, metric,
               transaction_type, granularity, account_id, sort_order
        FROM dashboard_widgets
        ORDER BY sort_order, id
    """)).mappings().all()
    widgets = []
    for row in rows:
        widgets.append({
            "id": str(row["id"]),
            "title": row["title"],
            "data_source": row["data_source"],
            "data_spec": row["data_spec"],
            "query": {
                "dimension": row["dimension"].lower(),
                "metric": row["metric"].lower(),
                "filters": {
                    "transaction_type": row["transaction_type"].lower() if row["transaction_type"] else None,
                    "account_id": row["account_id"],
                },
                "granularity": row["granularity"].lower() if row["granularity"] else None,
            },
            "visualization": {"type": row["type"].lower(), "options": {}},
        })

    dashboard_config = {"schema_version": 1, "widgets": widgets}
    connection.execute(
        sa.text("UPDATE app_settings SET dashboard_config = CAST(:config AS jsonb)"),
        {"config": json.dumps(dashboard_config)},
    )
    # A normal installation has the singleton row.  Keep the migration safe
    # for databases upgraded before the seed ran as well.
    connection.execute(
        sa.text("""
            INSERT INTO app_settings (
                id, currency, negative_cash_flow_threshold_months,
                net_worth_decline_threshold_months, risky_allocation_threshold_percent,
                idle_cash_threshold_amount, idle_cash_threshold_days, dashboard_config
            )
            SELECT 1, 'USD', 2, 2, 20, 1000, 60, CAST(:config AS jsonb)
            WHERE NOT EXISTS (SELECT 1 FROM app_settings WHERE id = 1)
        """),
        {"config": json.dumps(dashboard_config)},
    )
    op.alter_column("app_settings", "dashboard_config", nullable=False)
    op.drop_table("dashboard_widgets")


def downgrade() -> None:
    connection = op.get_bind()
    configs = connection.execute(sa.text("SELECT dashboard_config FROM app_settings")).scalars().all()
    for config in configs:
        for widget in (config or {}).get("widgets", []):
            query = widget.get("query", {})
            filters = query.get("filters", {})
            if (
                (config or {}).get("schema_version") != 1
                or not str(widget.get("id", "")).isdigit()
                or widget.get("data_source") != "transactions"
                or widget.get("data_spec") != "analytics"
                or widget.get("visualization", {}).get("options", {})
                or set(widget) != {"id", "title", "data_source", "data_spec", "query", "visualization"}
                or set(query) != {"dimension", "metric", "filters", "granularity"}
                or set(filters) != {"transaction_type", "account_id"}
            ):
                raise RuntimeError("Dashboard configuration cannot be represented by dashboard_widgets; downgrade aborted")
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_source", sa.String(length=50), nullable=False),
        sa.Column("data_spec", sa.String(length=80), nullable=False),
        sa.Column("type", sa.Enum("PIE", "BAR", "LINE", name="dashboard_widget_type", native_enum=False, length=10), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("dimension", sa.Enum("CATEGORY", "SUBCATEGORY", "ACCOUNT", "TAG", "TYPE", "TOTAL", name="dashboard_widget_dimension", native_enum=False, length=20), nullable=False),
        sa.Column("metric", sa.Enum("SUM", "COUNT", name="dashboard_widget_metric", native_enum=False, length=10), nullable=False),
        sa.Column("transaction_type", sa.Enum("INCOME", "EXPENSE", "TRANSFER", name="dashboard_widget_transaction_type", native_enum=False, length=10), nullable=True),
        sa.Column("granularity", sa.Enum("DAY", "WEEK", "MONTH", name="dashboard_widget_granularity", native_enum=False, length=20), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for config in configs:
        for order, widget in enumerate((config or {}).get("widgets", [])):
            query = widget["query"]
            filters = query["filters"]
            connection.execute(
                sa.text("""
                    INSERT INTO dashboard_widgets
                      (id, data_source, data_spec, type, title, dimension, metric,
                       transaction_type, granularity, account_id, sort_order)
                    VALUES (:id, :data_source, :data_spec, :type, :title, :dimension, :metric,
                            :transaction_type, :granularity, :account_id, :sort_order)
                """),
                {
                    "id": int(widget["id"]), "data_source": widget["data_source"],
                    "data_spec": widget["data_spec"], "type": widget["visualization"]["type"].upper(),
                    "title": widget["title"], "dimension": query["dimension"].upper(),
                    "metric": query["metric"].upper(),
                    "transaction_type": filters["transaction_type"].upper() if filters["transaction_type"] else None,
                    "granularity": query["granularity"].upper() if query["granularity"] else None,
                    "account_id": filters["account_id"], "sort_order": order,
                },
            )
    op.drop_column("app_settings", "dashboard_config")
