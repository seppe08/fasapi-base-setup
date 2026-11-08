# FastAPI Base Project: Setup Guide

This document explains how the base project is set up, what each piece does, and why we chose it. Use it as a reference when you start a new project.

---

## 1. Stack overview

| Tool | Purpose | Why we use it |
|---|---|---|
| **FastAPI** | Web framework | Fast, async-first, automatic validation and Swagger docs from type hints |
| **Pydantic v2** | Data validation | Validates request/response data using Python type hints |
| **pydantic-settings** | Config from env | Reads `.env` and environment variables into a typed object |
| **SQLAlchemy 2.0** | ORM | Maps Python classes to database tables; supports async |
| **asyncpg** | Postgres driver | Fast async driver that SQLAlchemy uses to talk to Postgres |
| **PostgreSQL** | Database | Reliable, widely used relational database |
| **Alembic** | Migrations | Versioned database schema changes, like Git for your tables |
| **pwdlib (argon2)** | Password hashing | Modern, secure hashing algorithm |
| **uv** | Package and env manager | Fast installs, one lock file, handles the virtual environment |
| **Docker Compose** | Local Postgres | Runs the database the same way on every machine |
| **pytest + pytest-asyncio** | Testing | Standard Python test runner with async support |
| **Ruff** | Linter and formatter | One fast tool that replaces flake8, isort and black |

---

## 2. Requirements

- **Python 3.12+**: required by our `pyproject.toml`.
- **Docker Desktop**: runs Postgres without installing it on Windows.
- **uv**: installs packages and manages `.venv` for you.

---

## 3. Project structure

```
base/
├── app/                    # All application code (the Python package)
│   ├── main.py             # App entry point: creates FastAPI, middleware, routers
│   ├── core/               # App-wide foundations (config, security)
│   │   ├── config.py       # Reads settings from .env
│   │   └── security.py     # Password hashing
│   ├── db/                 # Database plumbing
│   │   ├── base.py         # SQLAlchemy Base + naming convention
│   │   └── session.py      # Engine and session factory
│   ├── models/             # Database tables (SQLAlchemy)
│   │   ├── __init__.py     # Imports every model so Alembic sees them
│   │   └── user.py
│   ├── schemas/            # API data shapes (Pydantic)
│   │   └── user.py
│   └── api/                # HTTP layer
│       ├── deps.py         # Reusable dependencies (DB session, current user)
│       └── v1/
│           ├── router.py   # Collects all v1 routers
│           └── users.py    # User endpoints
├── alembic/                # Migration scripts and env.py
├── tests/                  # Automated tests
├── .env                    # Real secrets (never commit)
├── .env.example            # Safe template (commit this)
├── .gitignore
├── docker-compose.yml
└── pyproject.toml          # Project metadata and dependencies
```

**Why this layout?**
- **Separation of concerns:** database code, HTTP code and config never mix. A change to the database rarely touches your routes.
- **Scales well:** when the project grows, you add files to the right folder instead of making one huge `main.py`.
- **Versioned API (`api/v1/`):** when you later need breaking changes, you add `v2/` without breaking clients using `v1`.

---

## 4. Dependency management with uv

`pyproject.toml` is the single source of truth for dependencies.

- `dependencies`: packages the app needs to run.
- `dependency-groups.dev`: tools only used during development (pytest, ruff). They are not needed in production.
- Version lower bounds (`>=`) say "this version or newer". `uv.lock` pins the exact versions for everyone.

Common commands:

```powershell
uv add <package>          # add a runtime dependency
uv add --dev <package>    # add a dev-only dependency
uv remove <package>       # remove one
uv run <command>          # run a command inside .venv without activating it
uv sync                   # install everything from the lock file
```

**Why `fastapi[standard]`?** The `[standard]` extra installs uvicorn, the `fastapi` CLI, email validation and other common tools in one line.

**Why `pydantic[email]`?** It adds the `email-validator` package, which `EmailStr` needs.

---

## 5. Local database with Docker

`docker-compose.yml` starts Postgres in a container.

- `image: postgres:16`: pins the major version, so behaviour does not change unexpectedly.
- `ports: "5432:5432"`: exposes Postgres on `localhost:5432` so the app can connect.
- `volumes: pgdata`: keeps your data when the container restarts. Without it, every restart wipes the database.

Commands:

```powershell
docker compose up -d      # start in background
docker compose down       # stop (data is kept)
docker compose down -v    # stop and DELETE data
```

---

## 6. Environment variables (`.env`)

- **`.env`** holds real values for your machine. It must never be committed to Git because it can contain passwords.
- **`.env.example`** shows which variables exist, with fake values. It is committed so teammates know what to set.

```env
PROJECT_NAME=My API
ENVIRONMENT=local
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/appdb
CORS_ORIGINS=["http://localhost:3000"]
```

**Why `postgresql+asyncpg://`?** The part before `://` is the database type plus driver. `+asyncpg` tells SQLAlchemy to use the async driver.

**Why JSON for `CORS_ORIGINS`?** Pydantic parses list fields from `.env` as JSON.

---

## 7. Configuration (`app/core/config.py`)

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ...
```

- **Typed settings:** `DATABASE_URL: str` with no default means the app refuses to start if it's missing. Failing early is better than failing on the first request.
- **Defaults:** `PROJECT_NAME` and `ENVIRONMENT` have defaults, so they're optional.
- **`extra="ignore"`:** unknown variables in `.env` don't crash the app.
- **`@lru_cache`:** the settings are read once and reused everywhere, instead of re-reading the file on each call.
- **Why `pydantic_settings`, not `pydantic`?** In Pydantic v2, `BaseSettings` moved to the separate `pydantic-settings` package. That's why importing it from `pydantic` caused an error.

---

## 8. Database layer

### `app/db/base.py`: the Base and naming convention

```python
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)
```

- `Base` is the parent class of every model. Alembic reads its `metadata` to know all tables.
- **Naming convention:** gives constraints and indexes predictable names (for example `uq_users_email`). Without it, Postgres generates random names. Random names make later migrations that drop or change constraints hard to write, because you need to know the exact name.

### `app/db/session.py`: engine and session factory

```python
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

- **Engine:** one per app. It owns the connection pool, which reuses connections instead of opening a new one per request.
- **`pool_pre_ping=True`:** checks a connection is alive before using it. Useful after the database restarts.
- **Session:** one per request. It tracks the changes you make and writes them in one transaction when you call `commit()`.
- **`expire_on_commit=False`:** after `commit()`, objects keep their loaded values. Otherwise, accessing a field would trigger an extra database query, which fails in async code.

---

## 9. Models (`app/models/`)

`user.py` defines the `users` table as a Python class.

- **`Mapped[int]` and `mapped_column()`:** SQLAlchemy 2.0 style. The type hint defines the Python type, and `mapped_column` defines the database column.
- **`unique=True, index=True` on email:** the database rejects duplicate emails and searches by email are fast.
- **`hashed_password`:** we store a hash, never the plain password.
- **`server_default=func.now()`:** the database sets `created_at`, so it's always correct regardless of the app's clock.

`models/__init__.py` imports every model. Alembic only detects tables it has seen, so forgetting this import causes empty migrations.

---

## 10. Schemas (`app/schemas/`)

Schemas are Pydantic models that define what the API accepts and returns. They are separate from database models on purpose.

| Schema | Used for | Why |
|---|---|---|
| `UserCreate` | Input on POST | Includes `password`, which the client sends |
| `UserUpdate` | Input on PATCH | Only fields a user may change, so they can't change `is_active` or `email` |
| `UserRead` | Output | No `hashed_password`, so it never leaks |

- **`Field(min_length=8, ...)`:** validation rules declared once, enforced automatically, and shown in Swagger docs.
- **`EmailStr`:** validates email format.
- **`from_attributes=True`:** lets Pydantic read data from SQLAlchemy objects (`user.email` instead of `user["email"]`).

---

## 11. Security (`app/core/security.py`)

- **Hashing with pwdlib + argon2:** Argon2 is the recommended algorithm for passwords. It's slow on purpose so brute-force attacks are expensive.
- **Never store or log plain passwords.** Hash on the way in, verify on login.
- `hash_password` and `verify_password` are kept in one file so you can change the algorithm in one place.

---

## 12. Dependencies (`app/api/deps.py`)

FastAPI "dependencies" are functions that run before your route and pass their result in.

```python
DbSession = Annotated[AsyncSession, Depends(get_db)]
```

- **`get_db`** opens a session for the request and closes it afterwards, even if an error happens (`async with`).
- **`Annotated` aliases** (`DbSession`, `UserDep`): instead of repeating `Depends(get_db)` in every route, you write `db: DbSession`. Shorter and easier to change.
- **`get_user_or_404`** is reused across routes. It loads the user from `user_id` in the path and raises 404 if missing, so each route doesn't repeat that code.
- **Why dependencies?** They make code reusable and testable. In tests, you can replace `get_db` with a test database using `app.dependency_overrides`.

---

## 13. Routes (`app/api/v1/users.py`)

| Method | Path | Status | What it does |
|---|---|---|---|
| POST | `/users` | 201 | Create user |
| GET | `/users` | 200 | List users (paginated) |
| GET | `/users/{id}` | 200 | Get one user |
| PATCH | `/users/{id}` | 200 | Partial update |
| DELETE | `/users/{id}` | 204 | Delete user |

- **`response_model=UserRead`:** filters the output to the schema, so extra fields are removed.
- **Correct status codes:** 201 for created, 204 for "no content" on delete, 404 for not found, 409 for conflict (duplicate email). Clients rely on these.
- **`Query(0, ge=0)` and `Query(20, ge=1, le=100)`:** validates pagination. Users can't request negative skips or huge pages.
- **`model_dump(exclude_unset=True)`:** in PATCH, only the fields the client sent are changed. Without it, missing fields would be overwritten with `None`.
- **`prefix` and `tags`:** group routes in Swagger and keep paths consistent.

### `router.py`

Collects all v1 routers in one place. `main.py` only needs to include `api_router`, so adding a new resource means one line here.

---

## 14. App entry point (`app/main.py`)

- **`lifespan`:** code that runs at startup and shutdown. On shutdown we call `engine.dispose()` to close all database connections cleanly.
- **CORS middleware:** lets browsers on other origins (like a frontend on port 3000) call your API. Only origins in `CORS_ORIGINS` are allowed.
- **`include_router(api_router, prefix="/api/v1")`:** puts all endpoints under `/api/v1`.
- **`/health`:** a simple endpoint for monitoring tools and Docker to check the app is alive.

---

## 15. Migrations with Alembic

Alembic tracks database schema changes as versioned files in `alembic/versions/`.

**Why migrations instead of `create_all()`?** `Base.metadata.create_all()` only creates missing tables. It can't change or drop columns safely. Alembic records each change, so you can upgrade and downgrade and share the same schema with your team and production.

### Key files

- **`alembic.ini`:** settings file. The database URL here is a placeholder; the real URL comes from `.env`.
- **`alembic/env.py`:** the bridge between Alembic and your app:
  - `config.set_main_option("sqlalchemy.url", ...)`: uses the URL from `.env`. The `.replace("%", "%%")` escapes `%` characters, because Alembic's config parser treats `%` as special.
  - `target_metadata = Base.metadata`: tells autogenerate what the models should look like.
  - `compare_type=True`: detects column type changes, such as `String(100)` to `String(200)`.
  - `run_migrations_online()` uses the **async** engine, because our driver is asyncpg.

### Everyday workflow

| Task | Command |
|---|---|
| Create a migration after changing models | `uv run alembic revision --autogenerate -m "describe change"` |
| Apply all pending migrations | `uv run alembic upgrade head` |
| Undo the last migration | `uv run alembic downgrade -1` |
| See current version | `uv run alembic current` |
| See history | `uv run alembic history` |

**Golden rules:**
1. Always review the generated file before applying it.
2. Never edit a migration that has already been applied. Create a new one.
3. Commit migration files to Git.

---

## 16. Running the app

```powershell
uv run fastapi dev app/main.py
```

- `fastapi dev` runs with auto-reload for development.
- For production, use `fastapi run` or `uvicorn app.main:app --workers 4`, and turn reload off.
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

---

## 17. Testing

- **pytest** finds and runs tests in `tests/`.
- **pytest-asyncio** (`asyncio_mode = "auto"`) lets you write `async def` tests without extra decorators.
- **httpx `AsyncClient` with `ASGITransport`** calls the app in memory, with no server running.
- For database tests, use a separate test database and override `get_db` with `app.dependency_overrides`, so tests never touch your real data.

---

## 18. Code quality with Ruff

```powershell
uv run ruff check .      # find problems
uv run ruff check . --fix
uv run ruff format .     # format code
```

Rules we enabled in `pyproject.toml`:
- `E`, `F`: pycodestyle errors and pyflakes (unused imports, undefined names).
- `I`: sorted imports.
- `UP`: use modern Python syntax (like `list[str]` instead of `List[str]`).
- `B`: common bug patterns (like mutable default arguments).

---

## 19. Problems we solved (and why they happened)

| Error | Cause | Fix |
|---|---|---|
| `alembic` not recognized | Command ran outside the virtual environment | Use `uv run alembic ...` |
| `BaseSettings has been moved` | Pydantic v2 moved it to `pydantic-settings` | `from pydantic_settings import BaseSettings` |
| Empty migration generated | Models not imported in Alembic | `import app.models` in `env.py` and `models/__init__.py` |
| Alembic can't connect | `sqlalchemy.url` in `alembic.ini` is a placeholder | Set it from `settings.DATABASE_URL` in `env.py` |
| `DATABASE_URL field required` | `.env` missing or not in project root | Create `.env` in the root and run commands from there |
| Connection refused | Postgres not running | `docker compose up -d` |

---

## 20. Quick checklist for a new project

1. Create the project and add dependencies with `uv add`.
2. Create folders and `__init__.py` files.
3. Write `docker-compose.yml`, then `.env` and `.env.example`.
4. Write `config.py`, `base.py`, `session.py`.
5. Write the models and `models/__init__.py`.
6. Run `alembic init -t async alembic`, then edit `env.py`.
7. Run `docker compose up -d`, then `alembic revision --autogenerate` and `alembic upgrade head`.
8. Write schemas, security, deps, routes, router and `main.py`.
9. Run `uv run fastapi dev app/main.py` and check `/docs`.
10. Run `uv run ruff check . && uv run ruff format .` before each commit.