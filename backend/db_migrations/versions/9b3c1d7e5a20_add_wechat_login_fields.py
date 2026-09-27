"""add wechat login fields

Revision ID: 9b3c1d7e5a20
Revises: 7f2a1b9c4d3e
Create Date: 2026-09-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b3c1d7e5a20'
down_revision = '7f2a1b9c4d3e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        # 微信登录标识：openid 唯一，unionid 用于多应用打通
        batch_op.add_column(sa.Column('wechat_openid', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('wechat_unionid', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('avatar_url', sa.String(length=255), nullable=True))
        # 微信建号没有密码，password_hash 改为可空
        batch_op.alter_column('password_hash',
               existing_type=sa.String(length=255),
               nullable=True)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_users_wechat_openid'),
            ['wechat_openid'],
            unique=True,
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_wechat_openid'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash',
               existing_type=sa.String(length=255),
               nullable=False)
        batch_op.drop_column('avatar_url')
        batch_op.drop_column('wechat_unionid')
        batch_op.drop_column('wechat_openid')
