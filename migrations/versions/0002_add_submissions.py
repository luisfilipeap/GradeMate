"""Add submissions and the per-class composite keys they depend on

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL requires a unique constraint on the referenced columns before a
    # composite foreign key can point at them, so these come first.
    op.create_unique_constraint("uq_assessments_id_class", "assessments", ["id", "class_id"])
    op.create_unique_constraint("uq_students_id_class", "students", ["id", "class_id"])

    op.create_table(
        "submissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "class_id"],
            ["assessments.id", "assessments.class_id"],
            name="fk_submissions_assessment_id_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id", "class_id"],
            ["students.id", "students.class_id"],
            name="fk_submissions_student_id_students",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "assessment_id", "student_id", name="uq_submissions_assessment_student"
        ),
        sa.UniqueConstraint("file_path", name="uq_submissions_file_path"),
        # The naming convention expands these into "ck_submissions_<name>".
        sa.CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes > 0", name="file_size_positive"
        ),
        sa.CheckConstraint("page_count IS NULL OR page_count > 0", name="page_count_positive"),
    )
    op.create_index("ix_submissions_class_id", "submissions", ["class_id"])
    op.create_index("ix_submissions_assessment_id", "submissions", ["assessment_id"])
    op.create_index("ix_submissions_student_id", "submissions", ["student_id"])
    op.create_index("ix_submissions_checksum_sha256", "submissions", ["checksum_sha256"])


def downgrade() -> None:
    op.drop_index("ix_submissions_checksum_sha256", table_name="submissions")
    op.drop_index("ix_submissions_student_id", table_name="submissions")
    op.drop_index("ix_submissions_assessment_id", table_name="submissions")
    op.drop_index("ix_submissions_class_id", table_name="submissions")
    op.drop_table("submissions")
    op.drop_constraint("uq_students_id_class", "students", type_="unique")
    op.drop_constraint("uq_assessments_id_class", "assessments", type_="unique")
