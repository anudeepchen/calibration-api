from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Calibration, Membership

STAMP = "2026-09-15T10:00:00Z"


def create(client: TestClient, **overrides: object) -> dict:
    data = dict(
        calibration_type="offset",
        value="1.25000000000000000000000000001",
        username="alice",
        recorded_at=STAMP,
    )
    data.update(overrides)
    response = client.post("/calibrations", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_create(client: TestClient) -> None:
    item = create(
        client,
        username=" alice ",
        calibration_type=" offset ",
        recorded_at="2026-09-15T12:00:00+02:00",
    )
    assert item["recorded_at"] == STAMP
    assert item["value"] == "1.25000000000000000000000000001"
    assert item["username"] == "alice"
    start = datetime.now(timezone.utc)
    response = client.post(
        "/calibrations", json={"username": "bob", "calibration_type": "gain", "value": "2"}
    )
    assert response.status_code == 201
    assert start <= datetime.fromisoformat(response.json()["recorded_at"].replace("Z", "+00:00"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("recorded_at", "bad"),
        ("recorded_at", "2026-01-01T00:00:00"),
        ("recorded_at", None),
        ("username", " \t\n"),
        ("calibration_type", "\r\n"),
        ("value", "NaN"),
        ("value", "Infinity"),
        ("value", "-Infinity"),
        ("value", True),
        ("value", False),
        ("value", None),
        ("value", "not-a-number"),
    ],
)
def test_bad_create(client: TestClient, field: str, value: object) -> None:
    data = dict(username="alice", calibration_type="offset", value="1", recorded_at=STAMP)
    data[field] = value
    assert client.post("/calibrations", json=data).status_code == 422


def test_membership_history(client: TestClient, db: Session) -> None:
    item = create(client)
    path = f"/calibrations/{item['id']}/tags"
    first = client.post(path, json={"tag": " Ready "})
    assert first.status_code == 201
    member = first.json()
    duplicate = client.post(path, json={"tag": "Ready"})
    assert duplicate.status_code == 200
    assert duplicate.json() == member
    added = datetime.fromisoformat(member["added_at"].replace("Z", "+00:00"))
    for instant, expected in [
        (added - timedelta(microseconds=1), []),
        (added, ["Ready"]),
        (added + timedelta(days=365), ["Ready"]),
    ]:
        assert client.get(path, params={"as_of": instant.isoformat()}).json()["tags"] == expected
    assert client.delete(path, params={"tag": " Ready "}).status_code == 204
    assert client.delete(path, params={"tag": "Ready"}).status_code == 204
    old = db.get(Membership, UUID(member["id"]))
    removed = old.removed_at
    assert removed >= old.added_at
    for instant, expected in [
        (removed - timedelta(microseconds=1), ["Ready"]),
        (removed, []),
        (removed + timedelta(seconds=1), []),
    ]:
        assert client.get(path, params={"as_of": instant.isoformat()}).json()["tags"] == expected
    second = client.post(path, json={"tag": "Ready"}).json()
    assert second["id"] != member["id"]
    assert datetime.fromisoformat(second["added_at"].replace("Z", "+00:00")) >= removed
    assert db.scalar(select(func.count()).select_from(Membership)) == 2
    assert client.post(path, json={"tag": "ready"}).status_code == 201
    assert client.get(path).json() == {"tags": ["Ready", "ready"]}
    assert client.get(path, params={"as_of": second["added_at"]}).json() == {"tags": ["Ready"]}
    assert client.get(path, params={"as_of": "2026-01-01T00:00:00"}).status_code == 422


@pytest.mark.parametrize("method", ["get", "post", "delete"])
def test_missing(client: TestClient, method: str) -> None:
    path = f"/calibrations/{uuid4()}/tags"
    args = {"json": {"tag": "x"}} if method == "post" else {"params": {"tag": "x"}}
    assert getattr(client, method)(path, **args).status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"from_time": "bad"},
        {"from_time": "2026-01-01T00:00:00"},
        {"to_time": "2026-01-01T00:00:00"},
        {"tag": "x", "tag_as_of": "2026-01-01"},
        {"tag_as_of": STAMP},
        {"from_time": STAMP, "to_time": STAMP},
        {"from_time": "2027-01-01T00:00:00Z", "to_time": STAMP},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"tag": " \t"},
    ],
)
def test_bad_search(client: TestClient, params: dict) -> None:
    assert client.get("/calibrations", params=params).status_code == 422


def test_search(client: TestClient) -> None:
    a = create(client)
    b = create(client, username="bob", calibration_type="gain")
    c = create(client, recorded_at="2026-09-16T10:00:00Z")
    path = f"/calibrations/{a['id']}/tags"
    membership = client.post(path, json={"tag": "x"}).json()

    def ids(**params: object) -> list[str]:
        return [x["id"] for x in client.get("/calibrations", params=params).json()["items"]]

    assert set(ids(username=" alice ")) == {a["id"], c["id"]}
    assert ids(calibration_type="gain") == [b["id"]]
    assert ids(from_time="2026-09-16T10:00:00Z") == [c["id"]]
    assert set(ids(to_time="2026-09-16T10:00:00Z")) == {a["id"], b["id"]}
    assert ids(
        username="alice", calibration_type="offset", from_time=STAMP, to_time="2026-09-16T10:00:00Z"
    ) == [a["id"]]
    assert ids(tag=" x ") == [a["id"]]
    client.delete(path, params={"tag": "x"})
    assert ids(tag="x") == []
    assert ids(
        tag="x", tag_as_of=membership["added_at"], from_time=STAMP, to_time="2026-09-16T10:00:00Z"
    ) == [a["id"]]
    assert ids(username="absent") == []
    expected = [c["id"]] + sorted([a["id"], b["id"]], reverse=True)
    assert ids() == expected
    assert ids(limit=1, offset=1) == expected[1:2]
    page = client.get("/calibrations").json()
    assert (page["limit"], page["offset"]) == (50, 0)
    assert len(ids(limit=100)) == 3


def test_concurrent_add(client: TestClient, db: Session) -> None:
    item = create(client)
    barrier = Barrier(6)

    def add(_: int) -> int:
        barrier.wait(timeout=10)
        return client.post(f"/calibrations/{item['id']}/tags", json={"tag": "x"}).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(add, range(6)))
    assert sorted(statuses) == [200] * 5 + [201]
    rows = list(db.scalars(select(Membership)))
    assert len(rows) == 1
    assert rows[0].removed_at is None


@pytest.mark.parametrize("column", ["calibration_type", "username"])
@pytest.mark.parametrize("value", ["", " \t\n\r\f\v", None])
def test_calibration_constraints(db: Session, column: str, value: str | None) -> None:
    values = dict(
        id=uuid4(),
        calibration_type="offset",
        username="alice",
        value=1,
        recorded_at=datetime.now(timezone.utc),
    )
    values[column] = value
    with pytest.raises(IntegrityError), db.begin():
        db.add(Calibration(**values))
        db.flush()


@pytest.mark.parametrize("case", ["blank", "null", "fk", "duplicate", "interval"])
def test_membership_constraints(client: TestClient, db: Session, case: str) -> None:
    item = create(client)
    cid = UUID(item["id"])
    now = datetime.now(timezone.utc)
    row = dict(id=uuid4(), calibration_id=cid, tag="x", added_at=now)
    if case == "blank":
        row["tag"] = " \t\n\r\f\v"
    elif case == "null":
        row["tag"] = None
    elif case == "fk":
        row["calibration_id"] = uuid4()
    elif case == "interval":
        row["removed_at"] = now - timedelta(seconds=1)
    else:
        client.post(f"/calibrations/{cid}/tags", json={"tag": "x"})
    with pytest.raises(IntegrityError), db.begin():
        db.add(Membership(**row))
        db.flush()


def test_schema_is_migrated(db: Session) -> None:
    assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


def test_concurrent_add_remove(client: TestClient, db: Session) -> None:
    item = create(client)
    path = f"/calibrations/{item['id']}/tags"
    barrier = Barrier(8)

    def mutate(index: int) -> int:
        barrier.wait(timeout=10)
        if index % 2:
            return client.delete(path, params={"tag": "x"}).status_code
        return client.post(path, json={"tag": "x"}).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(mutate, range(8)))
    assert all(code in (200, 201, 204) for code in statuses)
    rows = list(db.scalars(select(Membership).order_by(Membership.added_at)))
    assert sum(row.removed_at is None for row in rows) <= 1
    for previous, following in zip(rows, rows[1:]):
        assert previous.removed_at is not None
        assert previous.removed_at <= following.added_at
    assert all(row.removed_at is None or row.removed_at >= row.added_at for row in rows)


def test_clock_regression(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import service

    item = create(client)
    path = f"/calibrations/{item['id']}/tags"
    first = client.post(path, json={"tag": "x"}).json()
    added = datetime.fromisoformat(first["added_at"].replace("Z", "+00:00"))

    class EarlierClock(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return added - timedelta(days=1)

    monkeypatch.setattr(service, "datetime", EarlierClock)
    assert client.delete(path, params={"tag": "x"}).status_code == 204
    old = db.get(Membership, UUID(first["id"]))
    assert old.removed_at == added
    second = client.post(path, json={"tag": "x"}).json()
    assert datetime.fromisoformat(second["added_at"].replace("Z", "+00:00")) == added


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.25", "1.25"),
        (1, "1"),
        (1.25, "1.25"),
        (-0.3, "-0.3"),
        (101.3, "101.3"),
        ("0.123456789012345678901234567890123456789", "0.123456789012345678901234567890123456789"),
    ],
)
def test_numeric_compatibility(
    client: TestClient, db: Session, value: object, expected: str
) -> None:
    from decimal import Decimal

    item = create(client, value=value)
    assert isinstance(item["value"], str)
    assert item["value"] == expected
    stored = db.get(Calibration, UUID(item["id"]))
    assert stored.value == Decimal(expected)
    assert client.get("/calibrations").json()["items"][0]["value"] == expected


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e1000", "-1e1000"])
def test_nonfinite_json_numbers(client: TestClient, db: Session, literal: str) -> None:
    response = client.post(
        "/calibrations",
        content='{"username":"alice","calibration_type":"offset","value":' + literal + "}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()
    assert db.scalar(select(func.count()).select_from(Calibration)) == 0


def test_original_assignment_workflow(client: TestClient, db: Session) -> None:
    # All fifteen optional sample rows from the original take-home, as JSON numbers.
    samples = [
        ("offset", 1.0, "alice"),
        ("gain", 1.5, "bob"),
        ("temperature", -0.3, "charlie"),
        ("offset", 0.9, "alice"),
        ("gain", 1.6, "dana"),
        ("offset", 1.2, "bob"),
        ("gain", 1.55, "alice"),
        ("temperature", -0.1, "charlie"),
        ("pressure", 101.3, "dana"),
        ("offset", 1.1, "alice"),
        ("gain", 1.4, "bob"),
        ("offset", 1.3, "charlie"),
        ("temperature", -0.2, "alice"),
        ("pressure", 100.8, "bob"),
        ("gain", 1.6, "charlie"),
    ]
    items = [
        create(client, calibration_type=kind, value=value, username=user)
        for kind, value, user in samples
    ]
    path = f"/calibrations/{items[0]['id']}/tags"
    assert client.get(path).json() == {"tags": []}
    # Tags need no registration and may contain spaces, punctuation, and Unicode.
    tag = "Production / ready: α"
    first = client.post(path, json={"tag": tag}).json()
    assert client.post(path, json={"tag": "backup"}).status_code == 201
    assert client.get(path).json() == {"tags": [tag, "backup"]}

    filters = dict(
        username="alice",
        calibration_type="offset",
        from_time=STAMP,
        to_time="2026-09-16T00:00:00Z",
        tag=tag,
    )
    assert client.get("/calibrations", params=filters).json()["items"] == [items[0]]
    assert client.delete(path, params={"tag": tag}).status_code == 204
    assert client.get("/calibrations", params=filters).json()["items"] == []
    assert client.get(path).json() == {"tags": ["backup"]}
    second = client.post(path, json={"tag": tag}).json()
    assert second["id"] != first["id"]
    # Both historical periods remain queryable after the second addition.
    for snapshot in (first["added_at"], second["added_at"]):
        assert client.get("/calibrations", params={**filters, "tag_as_of": snapshot}).json()[
            "items"
        ] == [items[0]]
    assert client.get(path, params={"as_of": first["added_at"]}).json() == {"tags": [tag]}
    assert db.scalar(select(func.count()).select_from(Calibration)) == 15
    periods = list(db.scalars(select(Membership).where(Membership.tag == tag)))
    assert len(periods) == 2
    assert sum(period.removed_at is None for period in periods) == 1


def test_integrity_conflict_is_controlled(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import service

    original = service.Calibration

    def duplicate_id(**values: object) -> Calibration:
        return original(id=UUID("00000000-0000-0000-0000-000000000001"), **values)

    monkeypatch.setattr(service, "Calibration", duplicate_id)
    create(client)
    payload = {"username": "alice", "calibration_type": "offset", "value": "1"}
    response = client.post("/calibrations", json=payload)
    assert response.status_code == 409
    assert response.json() == {"detail": "Database constraint conflict"}
    assert db.scalar(select(func.count()).select_from(Calibration)) == 1
    # A fresh request remains usable following the failed transaction.
    monkeypatch.setattr(service, "Calibration", original)
    create(client)
    assert db.scalar(select(func.count()).select_from(Calibration)) == 2
