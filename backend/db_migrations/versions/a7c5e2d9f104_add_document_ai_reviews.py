"""add document ai reviews

Revision ID: a7c5e2d9f104
Revises: 4b34825dc2e9
Create Date: 2026-10-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c5e2d9f104'
down_revision = '4b34825dc2e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_ai_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column('verdict', sa.String(length=16), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['requester_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['version_id'], ['document_versions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('document_ai_reviews', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_document_ai_reviews_created_at'),
            ['created_at'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_document_ai_reviews_document_id'),
            ['document_id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_document_ai_reviews_version_id'),
            ['version_id'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('document_ai_reviews', schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f('ix_document_ai_reviews_version_id')
        )
        batch_op.drop_index(
            batch_op.f('ix_document_ai_reviews_document_id')
        )
        batch_op.drop_index(
            batch_op.f('ix_document_ai_reviews_created_at')
        )

    op.drop_table('document_ai_reviews')
