"""Alertes : date jusqu'a laquelle l'utilisateur les a vues

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("alerts_seen_on", sa.Date(), nullable=True))


def downgrade():

    with op.batch_alter_table("users") as batch:
        batch.drop_column("alerts_seen_on")
