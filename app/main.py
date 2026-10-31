from datetime import datetime
from decimal import Decimal
from math import isfinite
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas, service
from app.db import get_session
from app.models import Calibration, Membership

app = FastAPI(
    title="Calibration API",
    description=(
        "Exact decimal values are returned as JSON strings. Membership intervals are [added_at, "
        "removed_at). Future snapshots reflect currently known state, not predicted changes."
    ),
)
DB = Annotated[Session, Depends(get_session)]
TimeQuery = Annotated[datetime, AfterValidator(schemas.utc)]
TextQuery = Annotated[str, AfterValidator(schemas.clean)]


@app.exception_handler(RequestValidationError)
async def validation_error(request: object, exc: RequestValidationError) -> JSONResponse:
    # Python's JSON decoder accepts nonstandard NaN/Infinity literals. Keep their
    # validation errors JSON-safe instead of failing while serializing a 422.
    detail = jsonable_encoder(
        exc.errors(),
        custom_encoder={
            Decimal: str,
            float: lambda value: value if isfinite(value) else str(value),
        },
    )
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(IntegrityError)
async def integrity_error(request: object, exc: IntegrityError) -> JSONResponse:
    # Session context managers roll back before this handler runs.
    return JSONResponse(status_code=409, content={"detail": "Database constraint conflict"})


@app.post("/calibrations", response_model=schemas.CalibrationOut, status_code=201)
def create(data: schemas.CalibrationCreate, session: DB) -> Calibration:
    return service.create_calibration(session, data)


@app.get("/calibrations", response_model=schemas.CalibrationPage)
def search(
    session: DB,
    username: TextQuery | None = None,
    calibration_type: TextQuery | None = None,
    from_time: TimeQuery | None = None,
    to_time: TimeQuery | None = None,
    tag: TextQuery | None = None,
    tag_as_of: TimeQuery | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(422, "from_time must precede to_time")
    if tag_as_of is not None and tag is None:
        raise HTTPException(422, "tag_as_of requires tag")
    return {
        "items": service.search(
            session, username, calibration_type, from_time, to_time, tag, tag_as_of, limit, offset
        ),
        "limit": limit,
        "offset": offset,
    }


@app.post(
    "/calibrations/{calibration_id}/tags",
    response_model=schemas.MembershipOut,
    status_code=201,
    responses={200: {"model": schemas.MembershipOut}},
)
def add(
    calibration_id: UUID, data: schemas.TagInput, response: Response, session: DB
) -> Membership:
    membership, created = service.add_tag(session, calibration_id, data.tag)
    response.status_code = 201 if created else 200
    return membership


@app.delete("/calibrations/{calibration_id}/tags", status_code=204)
def remove(calibration_id: UUID, tag: TextQuery, session: DB) -> Response:
    service.remove_tag(session, calibration_id, tag)
    return Response(status_code=204)


@app.get("/calibrations/{calibration_id}/tags", response_model=schemas.TagsOut)
def tags(calibration_id: UUID, session: DB, as_of: TimeQuery | None = None) -> dict[str, list[str]]:
    return {"tags": service.list_tags(session, calibration_id, as_of)}
