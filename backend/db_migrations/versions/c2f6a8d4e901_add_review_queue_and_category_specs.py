"""add review queue and category default specs

Revision ID: c2f6a8d4e901
Revises: a7c5e2d9f104
Create Date: 2026-10-20 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2f6a8d4e901'
down_revision = 'a7c5e2d9f104'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('document_categories', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('default_spec_document_ids', sa.JSON(), nullable=True)
        )

    with op.batch_alter_table('document_ai_reviews', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'status',
                sa.String(length=16),
                nullable=False,
                server_default='done',
            )
        )
        batch_op.add_column(
            sa.Column(
                'source',
                sa.String(length=16),
                nullable=False,
                server_default='manual',
            )
        )
        batch_op.add_column(
            sa.Column('spec_document_ids', sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('error_message', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('started_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('finished_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                'human_decision',
                sa.String(length=16),
                nullable=False,
                server_default='pending',
            )
        )
        batch_op.add_column(
            sa.Column('human_note', sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('human_reviewer_id', sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('human_reviewed_at', sa.DateTime(), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_document_ai_reviews_human_reviewer_id_users',
            'users',
            ['human_reviewer_id'],
            ['id'],
        )
        batch_op.create_index(
            batch_op.f('ix_document_ai_reviews_status'),
            ['status'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('document_ai_reviews', schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f('ix_document_ai_reviews_status')
        )
        batch_op.drop_constraint(
            'fk_document_ai_reviews_human_reviewer_id_users',
            type_='foreignkey',
        )
        batch_op.drop_column('human_reviewed_at')
        batch_op.drop_column('human_reviewer_id')
        batch_op.drop_column('human_note')
        batch_op.drop_column('human_decision')
        batch_op.drop_column('finished_at')
        batch_op.drop_column('started_at')
        batch_op.drop_column('error_message')
        batch_op.drop_column('spec_document_ids')
        batch_op.drop_column('source')
        batch_op.drop_column('status')

    with op.batch_alter_table('document_categories', schema=None) as batch_op:
        batch_op.drop_column('default_spec_document_ids')
