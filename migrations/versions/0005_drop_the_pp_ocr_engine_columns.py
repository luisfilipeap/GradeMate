"""Drop the PP-OCR engine columns

GradeMate now reads exams with PaddleOCR-VL only. The engine column existed to
tell the two pipelines apart, and confidence was only ever filled by PP-OCR:
PaddleOCR-VL reports no per-region score, so the column stayed NULL.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("confidence_range", "ocr_lines", type_="check")
    op.drop_column("ocr_lines", "confidence")
    op.drop_column("submission_pages", "engine")


def downgrade() -> None:
    op.add_column(
        "submission_pages",
        sa.Column("engine", sa.String(length=20), server_default="vl", nullable=False),
    )
    op.add_column("ocr_lines", sa.Column("confidence", sa.Float(), nullable=True))
    op.create_check_constraint(
        "confidence_range",
        "ocr_lines",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    )
