"""Add question_paper_ocr_pages

Holds the OCR transcript of an assessment's question paper (issue #32), one
string per page, produced by `POST .../question-paper/extract`. Nullable:
`None` means no extraction has been run yet, or the paper was replaced since
the last one that did.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessments",
        sa.Column(
            "question_paper_ocr_pages", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("assessments", "question_paper_ocr_pages")
