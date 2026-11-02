"""Mot de passe oublie (codes par e-mail) et mot de passe provisoire

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "password_reset_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_password_reset_codes_user_id_users",
            ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_codes")
    )

    op.create_index("ix_password_reset_codes_user_id", "password_reset_codes", ["user_id"])


def downgrade():

    op.drop_index("ix_password_reset_codes_user_id", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("must_change_password")
