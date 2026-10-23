"""link AI review revisions

Revision ID: d8f4c9b2e671
Revises: 4f7c2a1d9e30
Create Date: 2026-10-23 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d8f4c9b2e671"
down_revision = "4f7c2a1d9e30"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "document_ai_reviews", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column("previous_review_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_document_ai_reviews_previous_review_id",
            "document_ai_reviews",
            ["previous_review_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table(
        "document_ai_reviews", schema=None
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_document_ai_reviews_previous_review_id",
            type_="foreignkey",
        )
        batch_op.drop_column("previous_review_id")
