"""Add marketplace_installation table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(get_existing_tables())

    if "marketplace_installation" not in existing_tables:
        op.create_table(
            "marketplace_installation",
            sa.Column("id", sa.Text(), nullable=False, primary_key=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("skill_id", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False, server_default="clawhub"),
            sa.Column("external_slug", sa.Text(), nullable=False),
            sa.Column("external_owner", sa.Text(), nullable=True),
            sa.Column("installed_version", sa.Text(), nullable=False),
            sa.Column("latest_version", sa.Text(), nullable=True),
            sa.Column("auto_update", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("config", sa.JSON(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.UniqueConstraint(
                "user_id", "source", "external_slug", name="uq_user_source_slug"
            ),
        )
        op.create_index(
            "idx_marketplace_user_id",
            "marketplace_installation",
            ["user_id"],
        )
        op.create_index(
            "idx_marketplace_skill_id",
            "marketplace_installation",
            ["skill_id"],
        )


def downgrade() -> None:
    op.drop_index("idx_marketplace_skill_id", table_name="marketplace_installation")
    op.drop_index("idx_marketplace_user_id", table_name="marketplace_installation")
    op.drop_table("marketplace_installation")
