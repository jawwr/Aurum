"""add recurring_transaction_id to transactions

Revision ID: a3c9e7f1b502
Revises: d1a6f4c8b729
Create Date: 2026-09-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9e7f1b502'
down_revision: Union[str, None] = 'd1a6f4c8b729'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('recurring_transaction_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_transactions_recurring_transaction_id',
        'transactions',
        'recurring_transactions',
        ['recurring_transaction_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_transactions_recurring_transaction_id',
        'transactions',
        ['recurring_transaction_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_transactions_recurring_transaction_id', table_name='transactions')
    op.drop_constraint('fk_transactions_recurring_transaction_id', 'transactions', type_='foreignkey')
    op.drop_column('transactions', 'recurring_transaction_id')
