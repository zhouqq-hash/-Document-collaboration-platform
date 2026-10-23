"""add AI review templates

Revision ID: b3f7d1a9c642
Revises: d8f4c9b2e671
Create Date: 2026-10-23 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b3f7d1a9c642"
down_revision = "d8f4c9b2e671"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "document_categories", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_template_key",
                sa.String(length=64),
                nullable=False,
                server_default="generic_document_v1",
            )
        )

    with op.batch_alter_table(
        "document_ai_reviews", schema=None
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_template_key",
                sa.String(length=64),
                nullable=False,
                server_default="generic_document_v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "review_template_version",
                sa.String(length=16),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("checklist_json", sa.JSON(), nullable=True)
        )

    op.execute(
        "UPDATE document_categories "
        "SET review_template_key = 'syllabus_v1' "
        "WHERE name = '教学大纲'"
    )


def downgrade():
    with op.batch_alter_table(
        "document_ai_reviews", schema=None
    ) as batch_op:
        batch_op.drop_column("checklist_json")
        batch_op.drop_column("review_template_version")
        batch_op.drop_column("review_template_key")

    with op.batch_alter_table(
        "document_categories", schema=None
    ) as batch_op:
        batch_op.drop_column("review_template_key")
