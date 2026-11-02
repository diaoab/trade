"""Identite des comptes (prenom, nom, telephone) et activation

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("first_name", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("last_name", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("phone", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():

    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_active")
        batch.drop_column("phone")
        batch.drop_column("last_name")
        batch.drop_column("first_name")
