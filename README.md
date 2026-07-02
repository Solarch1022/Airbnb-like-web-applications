# Example Python Backend

A production-ready starter backend built with [FastAPI](https://fastapi.tiangolo.com/).

## Features

- FastAPI application using an application-factory pattern
- Environment-based configuration via `pydantic-settings`
- Layered structure: `routers` → `services` → `dao` → **AWS DynamoDB**
- Health-check endpoint and an example `items` CRUD resource persisted in DynamoDB
- DAO layer wrapping the `boto3` DynamoDB client (the only layer that touches AWS)
- CORS middleware
- Pytest test suite with `TestClient` and a fake in-memory DAO (no AWS needed)

## Project structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # App factory + entry point
│   ├── core/
│   │   └── config.py        # Settings loaded from env / .env
│   ├── models/              # Pydantic schemas
│   │   ├── health.py
│   │   └── item.py
│   ├── routers/             # API route definitions
│   │   ├── health.py
│   │   └── items.py
│   ├── services/            # Business logic
│   │   └── item_service.py
│   └── dao/                 # Data access (AWS DynamoDB via boto3)
│       └── item_dao.py
├── tests/                   # Pytest test suite
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

## Getting started

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements-dev.txt
   ```

3. (Optional) Create your local env file:

   ```bash
   cp .env.example .env
   ```

4. Run the development server:

   ```bash
   uvicorn app.main:app --reload
   ```

   Or:

   ```bash
   python -m app.main
   ```

The API will be available at http://localhost:8000. Interactive docs:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Endpoints

| Method | Path            | Description              |
| ------ | --------------- | ------------------------ |
| GET    | `/`             | Root / info              |
| GET    | `/health`       | Health check             |
| GET    | `/items`        | List all items           |
| POST   | `/items`        | Create an item           |
| GET    | `/items/{id}`   | Get an item by id        |
| DELETE | `/items/{id}`   | Delete an item by id     |

## Running tests

There are two tiers of tests:

```bash
# Fast unit tests only (mocks; no Docker/AWS needed):
pytest -m "not integration"

# Everything, including DynamoDB Local integration tests (needs Docker up):
docker compose up -d dynamodb-local
pytest

# Just the integration tests:
pytest -m integration
```

Integration tests connect to DynamoDB Local at `http://localhost:8000` (override
with `DYNAMODB_ENDPOINT_URL`). If the endpoint is not reachable, they are
**skipped** automatically, so a plain `pytest` stays green without Docker.

## DynamoDB setup

The DAO layer (`app/dao/item_dao.py`) reads/writes a DynamoDB table whose
**partition key is a string attribute named `id`**. Configure it via env vars
(see `.env.example`): `AWS_REGION`, `DYNAMODB_TABLE_NAME`, and optionally
`DYNAMODB_ENDPOINT_URL`. Credentials are resolved by `boto3`'s standard chain
(env vars, shared config, IAM role, etc.).

### Run the API locally against DynamoDB Local

The easiest path uses Docker Compose and the app's built-in table bootstrap
(`AUTO_CREATE_TABLE=true`), so **no AWS CLI is required**:

```bash
# 1. Start the local database
docker compose up -d dynamodb-local

# 2. Load local settings (points app at localhost:8000, enables auto-create)
cp .env.local .env

# 3. Run the API — the 'items' table is created on startup if missing
uvicorn app.main:app --reload
```

Then hit http://localhost:8000/docs and try `POST /items`.

Prefer everything in containers? Run the API in Docker too (talks to the
`dynamodb-local` service over the compose network):

```bash
docker compose --profile api up --build   # API on http://localhost:8080
```

> **Table bootstrap:** `ItemDAO.ensure_table()` creates the table when
> `AUTO_CREATE_TABLE=true` and `ENVIRONMENT != production`. In production,
> provision the table via infrastructure-as-code (CDK/CloudFormation/Terraform)
> and leave this off.

> Tests do **not** require AWS — they inject a fake in-memory DAO via FastAPI
> dependency overrides.

## Create-item example + mocks

A runnable script demonstrates the full create path
(`ItemService → ItemDAO → boto3 DynamoDB client`):

```bash
# Mocked (no AWS needed) — uses the in-memory FakeDynamoDBClient:
python -m examples.create_item_example

# Against a real endpoint (real AWS or DynamoDB Local):
DYNAMODB_ENDPOINT_URL=http://localhost:8000 python -m examples.create_item_example --real
```

### Reusable mocks (`tests/mocks.py`)

- **`FakeDynamoDBClient`** — an in-memory fake of the low-level
  `boto3.client("dynamodb")` (implements `put_item`, `get_item`, `delete_item`,
  and a `scan` paginator). Use it to test the **real** `ItemDAO`, exercising the
  attribute-value serialization without touching AWS.
- **`FakeItemDAO`** — a higher-level stand-in for `ItemDAO`, for testing the
  service/router layers with zero DynamoDB concerns.

Fixtures in `tests/conftest.py`:
- `client` → API wired to `FakeItemDAO`.
- `client_with_ddb_mock` + `ddb_client` → API wired to the real `ItemDAO` on top
  of `FakeDynamoDBClient` (see `tests/test_create_item.py`).

## Next steps

- Add authentication/authorization.
- Add pagination for the `list` (scan) endpoint or a GSI for query access patterns.
- Add a Dockerfile and infrastructure-as-code (CloudFormation/CDK/Terraform) for the table.
