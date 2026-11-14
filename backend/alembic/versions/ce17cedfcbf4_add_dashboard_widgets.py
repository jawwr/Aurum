"""add dashboard widgets

Revision ID: ce17cedfcbf4
Revises: a3c9e7f1b502
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce17cedfcbf4'
down_revision: Union[str, None] = 'a3c9e7f1b502'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dashboard_widgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            sa.Enum('PIE', 'BAR', 'LINE', name='dashboard_widget_type', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column(
            'dimension',
            sa.Enum(
                'CATEGORY', 'SUBCATEGORY', 'ACCOUNT', 'TAG', 'TYPE', 'TOTAL',
                name='dashboard_widget_dimension', native_enum=False, length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            'metric',
            sa.Enum('SUM', 'COUNT', name='dashboard_widget_metric', native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column(
            'transaction_type',
            sa.Enum(
                'INCOME', 'EXPENSE', 'TRANSFER',
                name='dashboard_widget_transaction_type', native_enum=False, length=10,
            ),
            nullable=True,
        ),
        sa.Column(
            'granularity',
            sa.Enum('DAY', 'WEEK', 'MONTH', name='dashboard_widget_granularity', native_enum=False, length=20),
            nullable=True,
        ),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('dashboard_widgets')
