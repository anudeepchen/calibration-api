# Architecture and requirements compliance

[Documentation index](README.md) · [Quick start](quickstart.md)

Assignment coverage, project structure, persistence design, and concurrency decisions.

## Original assignment requirements

The implementation was reviewed against **Senior Backend Engineer, ISW - Take
Home.pdf**. The original asks for a Python HTTP API, relational persistence, five
use cases, current/previous tag states, and instructions to run and verify it.

| Original requirement | Implementation | Verification |
| --- | --- | --- |
| Create a calibration with type, value, timestamp, and user | `POST /calibrations`; PostgreSQL NUMERIC and timezone-aware measurement time | Creation, numeric compatibility, validation, and persisted-value tests |
| Add a calibration to a tag | `POST /calibrations/{id}/tags`; new period or unchanged active period | Membership and concurrent duplicate-add tests |
| Remove a calibration from a tag | `DELETE /calibrations/{id}/tags`; closes rather than deletes a period | Membership, idempotency, and concurrent add/remove tests |
| Filter by one or more of user, time, type, and tag | `GET /calibrations`; AND-combined filters and optional `tag_as_of` | Search and original-assignment workflow tests |
| Query a calibration's tags | `GET /calibrations/{id}/tags`; optional `as_of` | Current, historical, empty, and multiple-tag tests |
| Retrieve current and previous tag states | Stored half-open membership periods, preserved across re-addition | Boundary tests and snapshots across both periods |
| Persist data relationally | PostgreSQL with an Alembic-managed schema | Database constraint and migration tests |
| Explain how to run and observe correctness | [Quick start](quickstart.md), [API examples](features.md), and [test instructions](testing.md) | PostgreSQL suite plus live API smoke verification |

The assignment's fifteen sample calibrations are optional seed data. They are
submitted as JSON numbers in `test_original_assignment_workflow`, which exercises
the five use cases and checks persisted state. They are not automatically loaded
into application databases. Tags require no registration and support internal
spaces, punctuation, and Unicode, while the later implementation requirements
normalize surrounding whitespace and reject blank tags.

The original prompt does not require authentication, a device registry, a
separate user table, or infrastructure beyond the service and database. Those
features have deliberately been left outside the scope.

## Repository structure

```text
app/
  main.py                  FastAPI application, routes, HTTP error handling
  schemas.py               Input validation and response schemas
  service.py               Queries, transactions, and membership behavior
  models.py                SQLAlchemy typed models, constraints, and indexes
  db.py                    Database engine, sessions, and configuration
alembic/
  env.py                   Migration environment
  versions/0001_initial.py Initial two-table schema
  script.py.mako           Template for future migrations
alembic.ini                Alembic configuration
compose.yaml               Local PostgreSQL 16 service
.env.example               Example application and test database URLs
pyproject.toml             Dependencies and tooling configuration
README.md                  Documentation index
quickstart.md              Installation and execution instructions
features.md                API reference and historical semantics
architecture.md            Requirements mapping and design decisions
deployment.md              Configuration, deployment, and migrations
testing.md                 Test instructions and verification results
tests/
  conftest.py              PostgreSQL migration and isolation fixtures
  test_api.py              HTTP, database, historical, and concurrency tests
```

## Database design and concurrent writes

`calibrations` has UUID primary key `id`, non-null text `calibration_type` and
`username`, non-null NUMERIC `value`, and non-null TIMESTAMPTZ `recorded_at`.

`calibration_tag_memberships` has UUID primary key `id`, non-null foreign key
`calibration_id`, non-null text `tag`, non-null TIMESTAMPTZ `added_at`, and nullable
TIMESTAMPTZ `removed_at`. One calibration can have many membership periods.

The initial migration adds:

- Primary keys, required-field constraints, and the calibration foreign key.
- Independent checks rejecting empty or ordinary-whitespace-only required text,
  including tabs, newlines, carriage returns, form feeds, and vertical tabs.
- An interval check requiring `removed_at IS NULL OR removed_at >= added_at`.
- A partial unique index on `(calibration_id, tag)` where `removed_at IS NULL`.
- Indexes for measurement ordering, exact user/type search, parent/tag lookup,
  and historical tag/time queries.

Every add/remove transaction locks the parent calibration using SELECT FOR UPDATE
before examining memberships. The service then reads a fresh UTC clock timestamp,
performs the mutation, and commits before reporting success. Both operations use
the same protocol, including idempotent requests. Mutations for different tags
on the same calibration also serialize; this keeps the implementation simple.

Removal timestamps are clamped to the addition timestamp. Re-addition timestamps
are clamped to the latest prior removal. These safeguards preserve interval
ordering if the application clock moves backward. The service uses neither
transaction-start PostgreSQL `now()` nor a custom monotonic clock.

The database's partial unique index is an independent active-membership safeguard.
Historical non-overlap also depends on following the service's locking protocol;
direct SQL writers must follow it too. The application assumes PostgreSQL's
default READ COMMITTED transaction isolation.

## Assumptions and trade-offs

Tag names and exact text filters are case-sensitive. No membership state is
inferred before the first recorded addition. All tag timestamps are service
controlled; callers cannot backdate membership events. Historical snapshots
reflect currently stored intervals, including for future query times.

Per-calibration locking deliberately favors straightforward correctness over
maximum write concurrency. Offset pagination favors a simple API over stable
pages during concurrent inserts. Dependencies have version ranges rather than a
checked-in lockfile. The project provides no automatic production schema setup,
authentication, deployment orchestration, or background infrastructure.
