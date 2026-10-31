"""Create calibrations and historical membership intervals."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("calibration_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(calibration_type, E' \\t\\n\\r\\f\\013')) > 0",
            name="ck_calibration_type_nonblank",
        ),
        sa.CheckConstraint(
            "length(btrim(username, E' \\t\\n\\r\\f\\013')) > 0", name="ck_username_nonblank"
        ),
    )
    op.create_index("ix_calibrations_recorded_id", "calibrations", ["recorded_at", "id"])
    op.create_index("ix_calibrations_username", "calibrations", ["username"])
    op.create_index("ix_calibrations_type", "calibrations", ["calibration_type"])
    op.create_table(
        "calibration_tag_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("calibration_id", sa.Uuid(), sa.ForeignKey("calibrations.id"), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("length(btrim(tag, E' \\t\\n\\r\\f\\013')) > 0", name="ck_tag_nonblank"),
        sa.CheckConstraint("removed_at IS NULL OR removed_at >= added_at", name="ck_interval"),
    )
    op.create_index(
        "uq_active_membership",
        "calibration_tag_memberships",
        ["calibration_id", "tag"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index(
        "ix_membership_tag_time", "calibration_tag_memberships", ["tag", "added_at", "removed_at"]
    )
    op.create_index(
        "ix_membership_calibration_tag", "calibration_tag_memberships", ["calibration_id", "tag"]
    )


def downgrade() -> None:
    op.drop_table("calibration_tag_memberships")
    op.drop_table("calibrations")
