# Ematiq assignment

## Lunch roulette

A web app where colleagues play for who pays lunch. Everyone in a room enters what their meal
costs (Kč, € or ₿), then players take turns opening cells on a grid. One cell hides a bomb, and
**whoever opens it pays for everybody**.

## Running it

```bash
docker compose up --build
```

Open http://localhost:8080, create an account, create a room and share the 6-character code
or link. To try it alone, use a second browser or an incognito window as another player.

Services:

| Service    | Port            | What it does                                         |
|------------|-----------------|------------------------------------------------------|
| `frontend` | `8080`          | nginx serving the React build, proxying `/api` + `/ws` |
| `backend`  | (internal 8000) | FastAPI, runs Alembic migrations on start            |
| `rates`    | `8001`          | Mock exchange-rate service                           |
| `postgres` | `5433`          | Postgres 17                                          |
| `mailpit`  | `8026`          | Catches outgoing email; inbox at http://localhost:8026 |

### Google sign-in (optional)

Create an OAuth client in Google Cloud (type "Web application") and register a redirect URI for every
address you open the app on, e.g. `http://localhost:8080/api/auth/google/callback` and, for a tunnel,
`https://<your-tunnel-host>/api/auth/google/callback`. The backend builds the redirect from the incoming
request, so no extra URL setting is needed. Then:

```bash
LUNCH_GOOGLE_CLIENT_ID=... LUNCH_GOOGLE_CLIENT_SECRET=... docker compose up --build
```

Until it's configured, the Google buttons are shown disabled. Logged-in players can also connect Google
to an existing account in **Settings**, and it then works as a backup sign-in if they forget their password.

### Local development

```bash
docker compose up -d postgres rates

cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/alembic upgrade head
.venv/bin/uvicorn lunch.main:app --reload       # :8000

cd frontend
npm install && npm run dev                        # :5173, proxies /api and /ws to :8000
```

### Tests and checks

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy                      # strict
.venv/bin/pytest --cov              # needs postgres on :5433; fails below 95% coverage
.venv/bin/alembic check             # migrations match the models
cd ../frontend
npm run typecheck
npm test                            # Vitest + Testing Library (jsdom)
npm run test:coverage               # with per-module coverage thresholds
```

The backend tests run against a real Postgres database (`lunch_test`, created automatically) through
the actual HTTP and WebSocket endpoints. External services are replaced with fakes: exchange rates,
SMTP, and Google OAuth.

### CI

`.github/workflows/ci.yml` runs on every push to `main` and on pull requests:

| Job | What it checks |
|---|---|
| Backend | ruff lint + format, `mypy --strict`, migrations (upgrade → `alembic check` → downgrade → upgrade), pytest with coverage against a Postgres service. Posts a coverage table to the run summary and uploads `coverage.xml` and `junit.xml` |
| Frontend | `npm ci`, type-check, unit tests with coverage thresholds, production build |
| Docker | all images in `docker-compose.yml` build |

## UI

The UI is built with [shadcn/ui](https://ui.shadcn.com) (Radix primitives + Tailwind v4) and themed with
Figma's **Neptune** palette plus one functional red. The colours carry meaning in the game:

| Colour | Hex | Used for |
|---|---|---|
| Electric indigo | `#525AFF` | primary actions, "your turn" |
| Teal | `#4AB5B5` | safe (opened) cells, winners, live indicator |
| Sky | `#8FD9FB` | hover, current player |
| Steel | `#6D8BC0` | secondary accents |
| Red | `#E0314B` | the bomb and whoever pays, nothing else |

Light and dark mode follow the OS setting. Theme tokens live in `frontend/src/index.css`.
