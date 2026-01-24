"""Initial migration with all models

Revision ID: 06fc1ceac590
Revises:
Create Date: 2026-01-24 14:48:29.250395

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '06fc1ceac590'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Only add the source column to shopping_item if it doesn't exist
    # Skip foreign key constraint changes (SQLite compatibility)
    try:
        with op.batch_alter_table('shopping_item', schema=None) as batch_op:
            batch_op.add_column(sa.Column('source', sa.String(length=20), nullable=True, server_default='manual'))
    except Exception:
        pass  # Column may already exist from legacy init_db migration


def downgrade():
    with op.batch_alter_table('shopping_item', schema=None) as batch_op:
        batch_op.drop_column('source')
