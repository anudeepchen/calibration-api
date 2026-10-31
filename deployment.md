# Configuration and deployment

[Documentation index](README.md) · [Quick start](quickstart.md)

For the shortest local setup, follow [quickstart.md](quickstart.md). This guide covers detailed configuration, deployment, migrations, and troubleshooting. Run commands from the repository root.

## Local installation and startup

Run the following commands from the repository root. The shell examples use
macOS/Linux syntax. You need Python 3.11 or newer and PostgreSQL, either native
or through Docker Compose. The local examples use port 5432.

### 1. Install dependencies

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

The `test` extra installs pytest, HTTPX, and Ruff in addition to the runtime
libraries. For a runtime-only installation, use `python -m pip install -e .`.
Activate the virtual environment in each new shell before running the commands
below.

### 2. Start PostgreSQL

```sh
docker compose up -d --wait
docker compose ps
```

Compose starts PostgreSQL 16 with database `calibration`, user `calibration`, and
password `calibration`, exposed on localhost port 5432. Data persists in the
`postgres_data` named volume. These credentials are for local development.
Compose runs the database only; the API runs separately in the virtual environment.

For setup without Docker, follow [Option B in the quick start](quickstart.md#option-b-native-postgresql-no-docker).
It includes native PostgreSQL installation guidance and SQL to create the
application role, application database, and disposable test database. The
remaining migration and Uvicorn commands are the same for both setups.

### 3. Configure the connection

```sh
cp .env.example .env
```

Do this once, or preserve an existing `.env` and edit it instead. The default file
contains:

```dotenv
DATABASE_URL=postgresql+psycopg://calibration:calibration@localhost:5432/calibration
TEST_DATABASE_URL=postgresql+psycopg://calibration:calibration@localhost:5432/calibration_test
```

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection URL used by the API and Alembic. |
| `TEST_DATABASE_URL` | Dedicated disposable PostgreSQL database used by pytest; export it in the shell before testing. |

Application configuration loads `.env`; existing environment variables take
precedence. Without `DATABASE_URL`, the application uses the local Compose URL
shown above. Tests require `TEST_DATABASE_URL` in the process environment before
application imports; merely adding it to `.env` is insufficient.

Use the `postgresql+psycopg://` URL scheme. Percent-encode special characters in
URL credentials. `.env` is ignored by version control.

### 4. Apply migrations

```sh
alembic upgrade head
alembic current
```

The database must already exist. Alembic creates the application tables and
indexes, plus its own migration version table. Starting Uvicorn does not run this
step automatically.

### 5. Start the API

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

Verify the application can query the database:

```sh
curl --fail --silent --show-error http://localhost:8000/calibrations
```

An empty database returns `{"items":[],"limit":50,"offset":0}`. A successful
OpenAPI request alone does not verify database connectivity.

### Stop local services

Press Ctrl+C in the Uvicorn terminal, then stop the database:

```sh
docker compose stop db
```

`docker compose down` also removes the Compose container and network while
retaining the named database volume. Adding `--volumes` deletes persisted local
database data; use that only for an intentional reset.

## Deployment beyond local development

The repository supplies a database Compose service and a Python application;
it does not include an application Docker image or platform-specific deployment
configuration. A straightforward deployment uses a Python host/process supervisor
and a reachable PostgreSQL database.

1. Provision a PostgreSQL database and credentials. Use deployment-specific
   credentials and configure database network access for the API host.
2. Copy the repository to the application host, create a Python 3.11+ virtual
   environment, and install runtime dependencies.
3. Inject `DATABASE_URL` through the deployment environment or secret store.
4. Run `alembic upgrade head` once as a release step before starting API instances.
5. Start Uvicorn under the host's process supervisor, without development reload.
6. Verify a database-backed request and inspect application/process logs.

Example commands on the deployment host, from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# Set DATABASE_URL in the deployment environment before these commands.
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Configure the supervisor to use this directory as its working directory, provide
the database environment, restart the process when needed, and capture stdout and
stderr. Put TLS and access controls at the deployment boundary where required:
this API has no built-in authentication and should not be exposed to untrusted
clients without such controls. Local Compose credentials are not production
credentials. Use your deployment's backup and recovery process before migrations.

A successful process start does not guarantee a usable database: connections are
opened on demand. Check both OpenAPI and a database-backed endpoint:

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/openapi.json > /tmp/calibration-openapi.json
curl --fail --silent --show-error http://127.0.0.1:8000/calibrations
```

There is no dedicated health-check route. Multiple API processes can use the
same database; PostgreSQL row locks coordinate their tag mutations. Each process
has its own SQLAlchemy connection pool, so account for that when choosing process
counts and database connection limits.

## Migrations

Run migrations from the repository root using the same `DATABASE_URL` as the API:

```sh
alembic current
alembic history
alembic upgrade head
```

For a future schema change, update the SQLAlchemy models, generate a candidate
migration, and review it before applying it:

```sh
alembic revision --autogenerate -m "describe the schema change"
alembic upgrade head
```

Autogeneration compares models with the connected database; use an appropriate
development database. Review constraints and PostgreSQL-specific indexes explicitly.
The initial migration's downgrade drops both application tables and their data;
it is not a routine rollback procedure for a populated deployment.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| Database connection refused | Confirm PostgreSQL is running, the host/port match `DATABASE_URL`, and the API host can reach it. |
| Port 5432 is already in use | Stop the conflicting local server or change Compose's host port and update both database URLs. |
| Relation does not exist | Run `alembic upgrade head` against the same database used by the API. |
| Authentication failed | Check the URL and actual database credentials. Changing Compose environment values does not update an already initialized database volume. |
| pytest requires `TEST_DATABASE_URL` | Export the variable in the shell; the test guard runs before `.env` is loaded. |
| Test database already exists | Skip `createdb` on subsequent runs and reuse the dedicated disposable test database. |
| Timestamp rejected with 422 | Include a timezone; URL-encode positive offsets instead of sending a literal `+`. |
| Decimal rejected with 422 | Send a finite decimal string or number, such as `"1.25"` or `1.25`; booleans, null, and non-finite values are invalid. |
| Historical query returns no tags | Compare the snapshot with the service-generated membership time, not only the calibration measurement time. |
| Root URL returns 404 | Use `/docs`, `/openapi.json`, or `/calibrations`; there is no root route. |
