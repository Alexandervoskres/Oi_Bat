"""purchase orders

Revision ID: 0003_orders
Revises: 0002_notifications
Create Date: 2026-06-17

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_orders"
down_revision = "0002_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("supplier_name", sa.String(length=160), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("total_amount", sa.Float(), server_default="0", nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_name", sa.String(length=160), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
    )
    op.create_index("ix_purchase_orders_id", "purchase_orders", ["id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_index("ix_purchase_orders_created_at", "purchase_orders", ["created_at"])

    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=80), server_default="", nullable=False),
        sa.Column("name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("purchase_price", sa.Float(), server_default="0", nullable=False),
        sa.Column("line_total", sa.Float(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("ix_purchase_order_items_id", "purchase_order_items", ["id"])
    op.create_index("ix_purchase_order_items_order_id", "purchase_order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_order_items_order_id", table_name="purchase_order_items")
    op.drop_index("ix_purchase_order_items_id", table_name="purchase_order_items")
    op.drop_table("purchase_order_items")
    op.drop_index("ix_purchase_orders_created_at", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
