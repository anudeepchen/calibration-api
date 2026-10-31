# Quick start

## Prerequisites

- Python 3.11 or newer.
- Either Docker with Compose v2 running **or** a native PostgreSQL server.
- Available ports 5432 and 8000.
- A macOS/Linux terminal or Windows WSL.

Run all commands from the extracted or cloned project directory.

## 1. Install dependencies

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

## 2. Configure and start PostgreSQL

For the first setup, copy the example configuration:

```sh
cp .env.example .env
```

Keep the default database URLs for either setup below. Preserve any existing
`.env` rather than overwriting it. If your shell already defines `DATABASE_URL`,
ensure it points to this project's database; shell variables override `.env`.

### Option A: Docker

```sh
docker compose up -d --wait
```

### Option B: Native PostgreSQL (no Docker)

Install PostgreSQL 16 using the [official platform instructions](https://www.postgresql.org/download/),
including the server and `psql` client. Start its database service using your
installer or operating system's service manager. Use localhost port 5432.

Connect as your PostgreSQL administrator (replace `YOUR_ADMIN_USER` with the role
created by your installation, often `postgres`; on macOS it may be your OS user):

```sh
psql -h localhost -U YOUR_ADMIN_USER -d postgres
```

Run these SQL statements at the `psql` prompt once, on a fresh local setup:

```sql
CREATE ROLE calibration WITH LOGIN PASSWORD 'calibration';
CREATE DATABASE calibration OWNER calibration;
CREATE DATABASE calibration_test OWNER calibration;
```

Exit with `\q`. These local credentials match `.env.example`. If these names
already exist, reuse them only if they belong to this project; otherwise choose
new names and update the URLs. The disposable test database name must end in
`_test`. Do not run Docker setup when using native PostgreSQL.

Verify the application role can connect; enter `calibration` when prompted:

```sh
psql -h localhost -U calibration -d calibration -c 'SELECT 1;'
```

Continue with the same migration and API commands below.

## 3. Apply migrations and run the API

```sh
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Keep this terminal open. Visit **http://localhost:8000/docs**.

## 4. Try the API

In Swagger UI:

1. Expand `POST /calibrations` and select **Try it out**.
2. Enter the following body and select **Execute**:

```json
{
  "calibration_type": "offset",
  "value": 1.25,
  "username": "alice"
}
```

3. Copy the `id` from the HTTP 201 response.
4. Use that ID with `POST /calibrations/{calibration_id}/tags` and this body:

```json
{"tag":"production-ready"}
```

5. Use `GET /calibrations` with `tag=production-ready` to find the calibration.
6. Use `GET /calibrations/{calibration_id}/tags` to list its tags.
7. Use `DELETE /calibrations/{calibration_id}/tags` with
   `tag=production-ready` to remove the membership.

## 5. Run tests and quality checks

For Docker users only, create the test database once:

```sh
docker compose exec db createdb -U calibration calibration_test
```

Native PostgreSQL users already created it in Option B. Open a second terminal
in the project directory and run the following for either setup:

```sh
source .venv/bin/activate
export TEST_DATABASE_URL='postgresql+psycopg://calibration:calibration@localhost:5432/calibration_test'
pytest -q
ruff check .
ruff format --check .
```

Run `createdb` only once. If `calibration_test` already exists, skip that command.
Tests erase data in the test database; use only the dedicated disposable URL
above. Keep the development `DATABASE_URL` separate from `TEST_DATABASE_URL`.

## 6. Stop

Press Ctrl+C in the API terminal. For Docker, stop the database with:

```sh
docker compose stop db
```

For native PostgreSQL, manage the database with your operating system service
manager; it can remain running for other applications.

## 7. Restart later

Start PostgreSQL using your chosen setup. Docker users run
`docker compose up -d --wait`; native users start their PostgreSQL service.
Then, from the project directory:

```sh
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## More documentation

- [Features and API examples](features.md), including historical queries.
- [Configuration, deployment, and troubleshooting](deployment.md).
- [Test coverage and verification](testing.md).
- [Documentation index](README.md).
