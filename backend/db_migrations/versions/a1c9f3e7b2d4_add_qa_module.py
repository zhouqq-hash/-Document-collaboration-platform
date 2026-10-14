"""add qa module

Revision ID: a1c9f3e7b2d4
Revises: 9b3c1d7e5a20
Create Date: 2026-10-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c9f3e7b2d4'
down_revision = '9b3c1d7e5a20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'qa_topics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('creator_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'qa_statements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.String(length=16), server_default='neutral', nullable=False),
        sa.Column('content', sa.String(length=2000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['topic_id'], ['qa_topics.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_qa_statements_topic_id'),
        'qa_statements',
        ['topic_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f('ix_qa_statements_topic_id'), table_name='qa_statements')
    op.drop_table('qa_statements')
    op.drop_table('qa_topics')
