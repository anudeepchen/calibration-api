# Testing and verification

[Documentation index](README.md) · [Quick start](quickstart.md)

PostgreSQL test isolation, focused tests, quality checks, and recorded verification results. Run commands from the repository root with the virtual environment active.

## Testing

### Prepare an isolated PostgreSQL database

Tests require a dedicated disposable database ending in `_test`. They apply
Alembic migrations at session start and **truncate both application tables before
each test**. Never point tests at valuable data, even if its name ends in `_test`.
Do not run test processes in parallel against the same database.

With the local Compose service already running:

```sh
source .venv/bin/activate
python -m pip install -e '.[test]'
docker compose exec db createdb -U calibration calibration_test
export TEST_DATABASE_URL='postgresql+psycopg://calibration:calibration@localhost:5432/calibration_test'
pytest -q
```

Create the test database only once; on subsequent runs, export the same URL and
run pytest again. The database role must be able to run migrations and truncate
the test tables. Tests refuse URLs that are missing, select a non-PostgreSQL
backend, lack an `_test` database suffix, or exactly equal an explicitly supplied
application `DATABASE_URL`. These checks do not replace careful URL selection.
There is no SQLite fallback.

For native PostgreSQL, follow [Option B in the quick start](quickstart.md#option-b-native-postgresql-no-docker)
to create the disposable test database; skip Docker commands and export its
`postgresql+psycopg://` URL instead. Inside the test process, the
fixtures direct the application and migration engine to this test database.

### Run focused tests and quality checks

```sh
pytest -q
pytest -q tests/test_api.py -k membership
pytest -q tests/test_api.py -k concurrent
ruff check .
ruff format --check .
```

To apply formatting locally, use `ruff format .`.

The integration suite checks:

- Creation defaults, timezone validation/normalization, blank inputs, numeric
  compatibility, exact decimal string preservation, and non-finite value rejection.
- All fifteen original assignment samples as JSON numbers; combined filters,
  arbitrary tag names, and both historical periods after re-addition.
- JSON-safe 422 responses for nonstandard NaN/Infinity literals and a controlled
  409 with rollback when a real database constraint is violated.
- Idempotent tag addition/removal, re-addition, preserved periods, trimming,
  case sensitivity, and missing calibrations.
- Snapshot boundaries before/at/after membership changes, future snapshots,
  and timestamps under clock regression.
- Combined user/type/measurement/tag filtering, inclusive/exclusive time bounds,
  empty results, validation, deterministic ordering, and pagination.
- Actual PostgreSQL foreign keys, NOT NULL and whitespace checks, active
  uniqueness, interval constraints, and the applied migration revision.
- Coordinated concurrent duplicate additions and mixed add/remove requests,
  including persisted active membership counts and non-overlapping periods.

The suite uses committed database sessions for concurrency tests, rather than
wrapping every request in a shared rollback-only transaction.

### Verify migrations on a fresh database

To validate schema creation independently, create a new disposable database and
explicitly select it for both migration and test commands:

```sh
docker compose exec db createdb -U calibration calibration_fresh_test
DATABASE_URL='postgresql+psycopg://calibration:calibration@localhost:5432/calibration_fresh_test' \
  alembic upgrade head
DATABASE_URL='postgresql+psycopg://calibration:calibration@localhost:5432/calibration_fresh_test' \
  alembic current
TEST_DATABASE_URL='postgresql+psycopg://calibration:calibration@localhost:5432/calibration_fresh_test' \
  pytest -q
```

Keep the surrounding shell's application `DATABASE_URL` pointed at its separate
application database. The one-command assignments above do not persist it.

### Recorded implementation verification

The final code review was verified with **57 passing PostgreSQL integration tests**,
passing Ruff lint/format checks, fresh-schema Alembic migration application, and
live Uvicorn requests to OpenAPI and calibration search. Docker was unavailable
in that environment, so these checks used an isolated native PostgreSQL instance.
The suite emitted one upstream Starlette TestClient/HTTPX deprecation warning.
These results describe the implementation verification, not a fresh execution
on every machine or deployment.
