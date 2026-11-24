"""company first EDGAR filing date

Revision ID: a1c3e5f7b9d2
Revises: f0f80e1e57cf
Create Date: 2026-10-29
"""
import sqlalchemy as sa
from alembic import op

revision = "a1c3e5f7b9d2"
down_revision = "f0f80e1e57cf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("first_filing_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "first_filing_date")
