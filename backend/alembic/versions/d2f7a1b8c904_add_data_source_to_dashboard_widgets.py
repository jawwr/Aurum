"""add data source and data spec identity to dashboard widgets

Revision ID: d2f7a1b8c904
Revises: ce17cedfcbf4
Create Date: 2026-11-14 00:00:00.000000

Existing widgets are transaction analytics widgets, so the migration fills
the new non-null columns with their explicit source/spec identities.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f7a1b8c904"
down_revision: Union[str, None] = "ce17cedfcbf4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dashboard_widgets",
        sa.Column("data_source", sa.String(length=50), nullable=False, server_default="transactions"),
    )
    op.add_column(
        "dashboard_widgets",
        sa.Column("data_spec", sa.String(length=80), nullable=False, server_default="analytics"),
    )
    op.alter_column("dashboard_widgets", "data_source", server_default=None)
    op.alter_column("dashboard_widgets", "data_spec", server_default=None)


def downgrade() -> None:
    op.drop_column("dashboard_widgets", "data_spec")
    op.drop_column("dashboard_widgets", "data_source")
