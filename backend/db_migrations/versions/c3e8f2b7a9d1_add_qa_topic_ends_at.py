"""add qa topic ends_at

Revision ID: c3e8f2b7a9d1
Revises: a1c9f3e7b2d4
Create Date: 2026-10-12 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e8f2b7a9d1'
down_revision = 'a1c9f3e7b2d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('qa_topics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ends_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('qa_topics', schema=None) as batch_op:
        batch_op.drop_column('ends_at')
