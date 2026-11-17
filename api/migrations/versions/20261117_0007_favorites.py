"""Titres favoris de l'utilisateur

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("favorites", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():

    with op.batch_alter_table("users") as batch:
        batch.drop_column("favorites")
