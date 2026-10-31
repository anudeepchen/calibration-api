from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def nonblank(column: str) -> str:
    return f"length(btrim({column}, E' \\t\\n\\r\\f\\013')) > 0"


class Calibration(Base):
    __tablename__ = "calibrations"
    __table_args__ = (
        CheckConstraint(nonblank("calibration_type"), name="ck_calibration_type_nonblank"),
        CheckConstraint(nonblank("username"), name="ck_username_nonblank"),
        Index("ix_calibrations_recorded_id", "recorded_at", "id"),
        Index("ix_calibrations_username", "username"),
        Index("ix_calibrations_type", "calibration_type"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    calibration_type: Mapped[str] = mapped_column(Text)
    value: Mapped[Decimal] = mapped_column(Numeric)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    username: Mapped[str] = mapped_column(Text)


class Membership(Base):
    __tablename__ = "calibration_tag_memberships"
    __table_args__ = (
        CheckConstraint(nonblank("tag"), name="ck_tag_nonblank"),
        CheckConstraint("removed_at IS NULL OR removed_at >= added_at", name="ck_interval"),
        Index(
            "uq_active_membership",
            "calibration_id",
            "tag",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        Index("ix_membership_tag_time", "tag", "added_at", "removed_at"),
        Index("ix_membership_calibration_tag", "calibration_id", "tag"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    calibration_id: Mapped[UUID] = mapped_column(ForeignKey("calibrations.id"))
    tag: Mapped[str] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
