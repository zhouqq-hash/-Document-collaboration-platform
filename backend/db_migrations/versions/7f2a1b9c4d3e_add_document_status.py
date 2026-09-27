"""add document status

Revision ID: 7f2a1b9c4d3e
Revises: df6013297280
Create Date: 2026-09-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f2a1b9c4d3e'
down_revision = 'df6013297280'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'status',
                sa.String(length=16),
                nullable=False,
                server_default='active',
            )
        )


def downgrade():
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_column('status')
