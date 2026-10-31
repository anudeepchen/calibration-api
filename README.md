# Calibration Backend API

A Python HTTP API for recording hardware calibration measurements, managing tags,
and querying current or historical tag membership. Removing and re-adding a tag
preserves its previous membership periods.

Built with Python 3.11+, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL, and Alembic.

## Start here

Follow **[quickstart.md](quickstart.md)** to install dependencies, start the API,
try endpoints in Swagger UI, and run the PostgreSQL integration tests.

You need Python 3.11+ and PostgreSQL, either installed natively or started with
Docker Compose. Docker is optional. No cloud account or API keys are required. Commands target macOS/Linux shells or Windows WSL.

## Documentation

| Document | What you will find |
| --- | --- |
| [Quick start](quickstart.md) | Copy-paste installation, startup, API trial, test, shutdown, and restart instructions. |
| [Features and API reference](features.md) | All five endpoints, curl examples, decimal formats, validation, filters, pagination, and historical time semantics. |
| [Architecture and requirements](architecture.md) | Original assignment coverage, source layout, database constraints, row locking, and design trade-offs. |
| [Configuration and deployment](deployment.md) | Environment variables, detailed local setup, deployment, Alembic migration commands, and troubleshooting. |
| [Testing and verification](testing.md) | Disposable PostgreSQL setup, test coverage, lint/format commands, fresh migration checks, and actual verification results. |

## Review snapshot

The final code review verified **57 passing PostgreSQL integration tests**, Ruff
linting and formatting, fresh-database migrations, schema/model consistency, and
live Uvicorn requests. Docker was unavailable during verification, so database
checks used native PostgreSQL.
See [testing.md](testing.md#recorded-implementation-verification) for context.

The API supports creating calibrations, adding/removing tags, searching with
combined filters, and listing tags at the current or a historical time. It stores
exact decimal strings as PostgreSQL NUMERIC and returns values as JSON strings;
finite JSON numeric inputs are also accepted.
