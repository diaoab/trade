"""Schema initial : comptes, positions, quota de l'assistant, paiements

Meme schema que celui cree auparavant par Base.metadata.create_all : une
base existante se rattache aux migrations par
    python -m alembic stamp 0001 && python -m alembic upgrade head

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("pro_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users")
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("buy_price", sa.Float(), nullable=False),
        sa.Column("buy_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_positions_user_id_users",
            ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_positions")
    )
    op.create_index("ix_positions_user_id", "positions", ["user_id"])

    op.create_table(
        "assistant_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_assistant_usage_user_id_users",
            ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_assistant_usage"),
        sa.UniqueConstraint("user_id", "day", name="uq_assistant_usage_user_id_day")
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("redirect_url", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_payments_user_id_users",
            ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payments")
    )
    op.create_index("ix_payments_token", "payments", ["token"], unique=True)
    op.create_index("ix_payments_user_id", "payments", ["user_id"])


def downgrade():

    op.drop_table("payments")
    op.drop_table("assistant_usage")
    op.drop_table("positions")
    op.drop_table("users")
