"""add project_type to game_project and create agent_project_auth table

Revision ID: 0004_project_type_and_agent_auth
Revises: 0003_add_user_max_devices
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_project_type_and_agent_auth'
down_revision = '0003_add_user_max_devices'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. game_project 加 project_type 字段
    op.add_column(
        'game_project',
        sa.Column(
            'project_type',
            sa.String(20),
            nullable=False,
            server_default='game',
            comment="项目类型：game=游戏项目（需独立库）/ verification=普通验证项目",
        ),
    )
    op.create_check_constraint(
        'chk_project_type_enum',
        'game_project',
        "project_type IN ('game', 'verification')",
    )

    # 2. db_name 改为可空（验证项目不需要独立数据库）
    op.alter_column('game_project', 'db_name', nullable=True)

    # 3. 新建代理项目授权表
    op.create_table(
        'agent_project_auth',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('agent_id', sa.Integer(),
                  sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.Integer(),
                  sa.ForeignKey('game_project.id', ondelete='CASCADE'), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True,
                  comment='NULL = 永久有效'),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('granted_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('agent_id', 'project_id', name='uq_agent_project'),
    )
    op.create_index('idx_agent_project_auth_agent', 'agent_project_auth', ['agent_id'])
    op.create_index('idx_agent_project_auth_project', 'agent_project_auth', ['project_id'])


def downgrade() -> None:
    op.drop_index('idx_agent_project_auth_project', 'agent_project_auth')
    op.drop_index('idx_agent_project_auth_agent', 'agent_project_auth')
    op.drop_table('agent_project_auth')
    op.alter_column('game_project', 'db_name', nullable=False)
    op.drop_constraint('chk_project_type_enum', 'game_project', type_='check')
    op.drop_column('game_project', 'project_type')
