# Qwantej

Football betting signals platform. Ingests live fixture and odds data from API-Football, runs Bayesian + Poisson probabilistic models to generate signals, scores and ranks them, and surfaces the best picks to subscribers via a React web app.

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.12+, async (asyncio) |
| Database | SQLite via aiosqlite + SQLAlchemy 2.x async ORM |
| Task queue | APScheduler (AsyncIOScheduler) |
| Frontend | React 18 + Vite, Tailwind CSS |
| Auth | JWT + bcrypt, tier-gated features |
| Payments | Paystack webhook integration |
| Data source | API-Football |
| Hosting | Fly.io |

## Local development

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env       # then fill in API keys
python run.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:8010`, frontend on `http://localhost:5173`.

Set `SKIP_STARTUP_SYNC=true` in `backend/.env` during development to avoid spending API quota on every hot-reload restart.

## Deployment

The app deploys to Fly.io as a single Docker container (frontend built into `frontend_dist/` and served by FastAPI).

```bash
flyctl deploy
```

The `Dockerfile` and `fly.toml` are already configured. The `docker-entrypoint.sh` handles DB staging and swapping on Fly.io volumes.

## Admin setup

Create or reset the admin user on the live database:

```bash
fly ssh console -a qwantej -C "cd /app && python create_admin.py <email> <password>"
```

## Architecture

See [CLAUDE.md](CLAUDE.md) for the full architecture, data flow, signal ranking logic, scheduler schedule, and development conventions.
