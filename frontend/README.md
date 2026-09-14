# Plan2Progress — Frontend

React + TypeScript + Vite + Tailwind frontend for the SIH26122 AI-Powered
Planning-to-Execution Project Progress Intelligence Platform (Team SyncForge).
Talks to the existing FastAPI backend in `../backend` — see
[`../FRONTEND_API_INTEGRATION.md`](../FRONTEND_API_INTEGRATION.md) for the full
endpoint inventory this UI was built against.

## Run it

Backend first (from `../backend`, with Postgres and Redis reachable, `.env`
configured — see `backend/README.md` and `docs/START-GUIDE.md`):

```bash
source .venv/bin/activate
alembic upgrade head            # first time only
python -m app.cli create-admin --email you@example.com --password "..." --full-name "You"
uvicorn app.main:app --reload --port 8000
celery -A app.worker worker --loglevel=info   # needed for document/matching/ML jobs
```

Then the frontend:

```bash
npm install
cp .env.example .env   # set VITE_API_BASE_URL if the backend isn't on localhost:8000
npm run dev
```

Open http://localhost:5173. Backend CORS (`backend/.env`) already allows this
origin by default (`CORS_ORIGINS=http://localhost:3000,http://localhost:5173`).

## Structure

- `src/api/` — one module per backend router, thin wrappers over a shared
  `axios` client (`client.ts`) with automatic access-token refresh.
- `src/types/api.ts` — TypeScript types mirroring the backend Pydantic schemas.
- `src/context/` — auth session and current-project context.
- `src/components/layout/` — app shell (nav, notifications) and the
  per-project tab layout.
- `src/pages/` — one file per screen; `src/pages/project/` holds everything
  scoped to a single project (schedule, matching, risk, reports, etc).

## Notes

- Every number on screen comes from a backend response — there is no mock
  data or hardcoded demo content anywhere in this app.
- The Voice Assistant screen intentionally does not embed a Vapi widget: the
  backend has no endpoint that hands the browser a session/key for one. See
  `FRONTEND_API_INTEGRATION.md` for what is and isn't wired up there.
