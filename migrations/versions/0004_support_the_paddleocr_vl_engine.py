"""Support the PaddleOCR-VL engine

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PaddleOCR-VL labels each region it reads and gives it no confidence score.
    op.add_column("ocr_lines", sa.Column("label", sa.String(length=40), nullable=True))
    op.alter_column("ocr_lines", "confidence", existing_type=sa.Float(), nullable=True)
    # The naming convention expands this into "ck_ocr_lines_confidence_range".
    op.drop_constraint("confidence_range", "ocr_lines", type_="check")
    op.create_check_constraint(
        "confidence_range",
        "ocr_lines",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    )

    # Which engine produced the reading of a page.
    op.add_column(
        "submission_pages",
        sa.Column("engine", sa.String(length=20), server_default="ocr", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("submission_pages", "engine")
    # The naming convention expands this into "ck_ocr_lines_confidence_range".
    op.drop_constraint("confidence_range", "ocr_lines", type_="check")
    op.execute("DELETE FROM ocr_lines WHERE confidence IS NULL")
    op.alter_column("ocr_lines", "confidence", existing_type=sa.Float(), nullable=False)
    op.create_check_constraint(
        "confidence_range", "ocr_lines", "confidence >= 0 AND confidence <= 1"
    )
    op.drop_column("ocr_lines", "label")
