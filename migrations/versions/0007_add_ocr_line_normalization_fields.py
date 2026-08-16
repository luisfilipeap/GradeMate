"""Add OCR line normalization fields

`normalized_text` holds the LLM's LaTeX/Markdown proposal for a line (issue
#21), kept apart from `corrected_text` because that column already means "the
teacher edited this" and a normalization is a machine proposal, not an edit.
`normalization_incomplete` flags a line whose normalization did not produce a
usable `normalized_text` (service unreachable, timeout, malformed response,
or the semantic guard rejecting the proposal), so the review screen can warn
the teacher without touching `text` or blocking the existing accept/rewrite
flow.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ocr_lines", sa.Column("normalized_text", sa.Text(), nullable=True))
    op.add_column(
        "ocr_lines",
        sa.Column(
            "normalization_incomplete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # The server default only exists to backfill existing rows; new rows
    # should always state the value explicitly, same as `accepted`.
    op.alter_column("ocr_lines", "normalization_incomplete", server_default=None)


def downgrade() -> None:
    op.drop_column("ocr_lines", "normalization_incomplete")
    op.drop_column("ocr_lines", "normalized_text")
