"""Role des comptes (back-office) et date de derniere connexion

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():

    # batch_alter_table : SQLite ne sait pas modifier une table en place.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(length=20), nullable=False, server_default="user"))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():

    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_login_at")
        batch.drop_column("role")
