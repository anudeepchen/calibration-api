from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import Calibration, Membership
from app.schemas import CalibrationCreate


def create_calibration(session: Session, data: CalibrationCreate) -> Calibration:
    with session.begin():
        calibration = Calibration(**data.model_dump())
        session.add(calibration)
        session.flush()
    return calibration


def require_calibration(session: Session, calibration_id: UUID, lock: bool = False) -> Calibration:
    query = select(Calibration).where(Calibration.id == calibration_id)
    if lock:
        query = query.with_for_update()
    calibration = session.scalar(query)
    if calibration is None:
        raise HTTPException(404, "Calibration not found")
    return calibration


def membership_condition(as_of: datetime | None) -> ColumnElement[bool]:
    if as_of is None:
        return Membership.removed_at.is_(None)
    return (Membership.added_at <= as_of) & or_(
        Membership.removed_at.is_(None), Membership.removed_at > as_of
    )


def add_tag(session: Session, calibration_id: UUID, tag: str) -> tuple[Membership, bool]:
    with session.begin():
        require_calibration(session, calibration_id, lock=True)
        pair = (Membership.calibration_id == calibration_id, Membership.tag == tag)
        active = session.scalar(select(Membership).where(*pair, Membership.removed_at.is_(None)))
        if active is not None:
            return active, False
        previous_end = session.scalar(select(func.max(Membership.removed_at)).where(*pair))
        timestamp = datetime.now(timezone.utc)
        if previous_end is not None:
            timestamp = max(timestamp, previous_end)
        membership = Membership(calibration_id=calibration_id, tag=tag, added_at=timestamp)
        session.add(membership)
        session.flush()
    return membership, True


def remove_tag(session: Session, calibration_id: UUID, tag: str) -> None:
    with session.begin():
        require_calibration(session, calibration_id, lock=True)
        active = session.scalar(
            select(Membership).where(
                Membership.calibration_id == calibration_id,
                Membership.tag == tag,
                Membership.removed_at.is_(None),
            )
        )
        if active is not None:
            active.removed_at = max(datetime.now(timezone.utc), active.added_at)


def search(
    session: Session,
    username: str | None,
    calibration_type: str | None,
    from_time: datetime | None,
    to_time: datetime | None,
    tag: str | None,
    tag_as_of: datetime | None,
    limit: int,
    offset: int,
) -> list[Calibration]:
    query: Select[tuple[Calibration]] = select(Calibration)
    for column, value in (
        (Calibration.username, username),
        (Calibration.calibration_type, calibration_type),
    ):
        if value is not None:
            query = query.where(column == value)
    if from_time is not None:
        query = query.where(Calibration.recorded_at >= from_time)
    if to_time is not None:
        query = query.where(Calibration.recorded_at < to_time)
    if tag is not None:
        query = query.where(
            select(Membership.id)
            .where(
                Membership.calibration_id == Calibration.id,
                Membership.tag == tag,
                membership_condition(tag_as_of),
            )
            .exists()
        )
    return list(
        session.scalars(
            query.order_by(Calibration.recorded_at.desc(), Calibration.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def list_tags(session: Session, calibration_id: UUID, as_of: datetime | None) -> list[str]:
    require_calibration(session, calibration_id)
    return sorted(
        set(
            session.scalars(
                select(Membership.tag).where(
                    Membership.calibration_id == calibration_id, membership_condition(as_of)
                )
            )
        )
    )
