"""Initial schema: classes, students and assessments

Revision ID: 0001
Revises:
Create Date: 2026-08-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=True),
        sa.Column("academic_term", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_classes"),
        sa.UniqueConstraint("code", name="uq_classes_code"),
    )
    op.create_index("ix_classes_academic_term", "classes", ["academic_term"])

    op.create_table(
        "students",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("registration_number", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_students"),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            name="fk_students_class_id_classes",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "class_id", "registration_number", name="uq_students_class_registration"
        ),
        sa.UniqueConstraint("class_id", "email", name="uq_students_class_email"),
    )
    op.create_index("ix_students_class_id", "students", ["class_id"])

    op.create_table(
        "assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("class_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applied_on", sa.Date(), nullable=True),
        sa.Column(
            "max_score",
            sa.Numeric(precision=6, scale=2),
            server_default="100",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_assessments"),
        sa.ForeignKeyConstraint(
            ["class_id"],
            ["classes.id"],
            name="fk_assessments_class_id_classes",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("class_id", "title", name="uq_assessments_class_title"),
        # The metadata naming convention expands this into
        # "ck_assessments_max_score_positive".
        sa.CheckConstraint("max_score > 0", name="max_score_positive"),
    )
    op.create_index("ix_assessments_class_id", "assessments", ["class_id"])


def downgrade() -> None:
    op.drop_index("ix_assessments_class_id", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index("ix_students_class_id", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_classes_academic_term", table_name="classes")
    op.drop_table("classes")
