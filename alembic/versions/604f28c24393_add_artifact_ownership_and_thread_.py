"""add_artifact_ownership_and_thread_columns

Revision ID: 604f28c24393
Revises: e9f1a2b3c4d5
Create Date: 2026-06-10 22:35:58.679843
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '604f28c24393'
down_revision: str | Sequence[str] | None = 'e9f1a2b3c4d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('artifacts', sa.Column('created_by_user_id', sa.UUID(), nullable=True))
    op.add_column('artifacts', sa.Column('updated_by_user_id', sa.UUID(), nullable=True))
    op.add_column('artifacts', sa.Column('thread_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_artifacts_created_by_user_id'), 'artifacts', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_artifacts_thread_id'), 'artifacts', ['thread_id'], unique=False)
    op.create_index(op.f('ix_artifacts_updated_by_user_id'), 'artifacts', ['updated_by_user_id'], unique=False)
    op.create_foreign_key(op.f('fk_artifacts_updated_by_user_id_users'), 'artifacts', 'users', ['updated_by_user_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_artifacts_created_by_user_id_users'), 'artifacts', 'users', ['created_by_user_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_artifacts_thread_id_threads'), 'artifacts', 'threads', ['thread_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_artifacts_thread_id_threads'), 'artifacts', type_='foreignkey')
    op.drop_constraint(op.f('fk_artifacts_created_by_user_id_users'), 'artifacts', type_='foreignkey')
    op.drop_constraint(op.f('fk_artifacts_updated_by_user_id_users'), 'artifacts', type_='foreignkey')
    op.drop_index(op.f('ix_artifacts_updated_by_user_id'), table_name='artifacts')
    op.drop_index(op.f('ix_artifacts_thread_id'), table_name='artifacts')
    op.drop_index(op.f('ix_artifacts_created_by_user_id'), table_name='artifacts')
    op.drop_column('artifacts', 'thread_id')
    op.drop_column('artifacts', 'updated_by_user_id')
    op.drop_column('artifacts', 'created_by_user_id')
