"""add table cell metadata for formulas and import locks

Revision ID: 4f7c2a1d9e30
Revises: c2f6a8d4e901
Create Date: 2026-10-23 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4f7c2a1d9e30"
down_revision = "c2f6a8d4e901"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tables", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cell_meta", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("tables", schema=None) as batch_op:
        batch_op.drop_column("cell_meta")
