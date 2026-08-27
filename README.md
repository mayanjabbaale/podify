# Podify

PDF → Audiobook / Podcast converter. Self-hosted. Local TTS (Kokoro). Gemini
free tier for podcast script generation. SQLite by default; Postgres optional.

See `idea.md` for the full project brief.

## Status

**Milestone 1 — Skeleton.** FastAPI + Celery + Redis + SQLite, models, migrations,
health check, minimal upload page. Feature work (PDF upload, extraction, TTS,
Gemini scripting) lands in M2–M6.

## Prerequisites (Windows 11)

| Tool | Install | Why |
|---|---|---|
| Python 3.13 | python.org installer | Runtime |
| Docker Desktop | docker.com | Runs Redis + optional Postgres in containers |
| ffmpeg | `winget install ffmpeg` | Required by pydub for mp3 output. **Restart your terminal after install** so PATH is picked up. |
| espeak-ng | `winget install espeak-ng` | Required by Kokoro TTS (M3+). Verify with `espeak-ng --version`. |

System tools can be verified at any time:

```powershell
ffmpeg -version
espeak-ng --version
docker --version
```

## First-time setup

```powershell
# 1. Activate the existing venv
.venv\Scripts\Activate.ps1

# 2. Install Python dependencies
python -m pip install -r requirements.txt

# 3. Copy the env template and fill in GEMINI_API_KEY
copy .env.example .env
notepad .env   # paste your free-tier key from https://aistudio.google.com/apikey

# 4. Start Redis (and Postgres, if you want it)
docker compose up -d redis postgres

# 5. Run database migrations
python -m alembic upgrade head

# 6. Create runtime storage dirs
New-Item -ItemType Directory -Force -Path storage\pdfs,storage\audio,storage\tts_cache,storage\models\kokoro | Out-Null
```

### About `GEMINI_API_KEY`

As of June 19, 2026, the Gemini API **rejects unrestricted API keys**. Get
your key from [Google AI Studio](https://aistudio.google.com/apikey) and
restrict it (HTTP referrer / IP / Android app). Don't enable billing on the
project — doing so deletes the free tier and makes every call billable from
token one.

### About Kokoro model files (M3+)

`kokoro-onnx` does not auto-download its ONNX model. When Milestone 3 lands:

1. Download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the
   [`hexgrad/kokoro` `model-files-v1.1` release](https://github.com/hexgrad/kokoro/releases/tag/model-files-v1.1).
2. Drop them into `storage/models/kokoro/`.
3. The app picks them up via `KOKORO_MODEL_DIR` in `.env`.

## Running the app

Two terminals — one for the API, one for the Celery worker.

**Terminal A — FastAPI:**

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal B — Celery worker** *(the `-P solo` flag is REQUIRED on Windows — Celery's default prefork pool doesn't work without fork())*:

```powershell
.venv\Scripts\celery.exe -A app.tasks.celery_app worker -P solo -l info
```

## Smoke tests

```powershell
# Health check — expect {"status":"ok","db":"ok","redis":"ok"} and HTTP 200
curl http://127.0.0.1:8000/health

# Submit the stub Celery task
.venv\Scripts\python.exe -c "from app.tasks import ping; print(ping.delay().get(timeout=10))"
# Expect: pong

# Run pytest
.venv\Scripts\python.exe -m pytest tests/ -v

# Open the upload page in your browser
start http://127.0.0.1:8000/
```

## Switching to Postgres (optional)

The default `DATABASE_URL` in `.env.example` is SQLite. To use Postgres:

```powershell
# Update .env
# DATABASE_URL=postgresql+psycopg://podify:podify@localhost:5432/podify

# Add the Postgres driver to requirements (SQLAlchemy needs psycopg, not psycopg2)
.venv\Scripts\python.exe -m pip install "psycopg[binary]>=3.1"

# Re-run migrations
.venv\Scripts\python.exe -m alembic upgrade head
```

8GB of RAM is the design point — SQLite is recommended unless you're scaling
beyond a single machine.

## Troubleshooting

### Celery worker crashes with "not enough values to unpack (expected 3, got 0)"

You're missing `-P solo`. Windows has no `fork()`, so Celery's default pool
won't work. Always use `-P solo`.

### `/health` returns `redis: error`

Either the Redis container isn't running (`docker compose ps` to check) or
the port in `.env` doesn't match. Default is `redis://localhost:6379/0`.

### `pydub` complains about ffmpeg

Install it (`winget install ffmpeg`) and **restart the terminal/Python
process** so the new PATH is picked up. Verify with `ffmpeg -version`.

### SQLite "database is locked" errors

Shouldn't happen with WAL mode enabled (it is, in `app/db.py`). If it does,
check that no long-running query is holding a write transaction.

## Project layout

See `app/` for the FastAPI application, `alembic/` for migrations, `tests/`
for pytest suites, and `storage/` for runtime data (gitignored).

## Build sequence

| Milestone | Status | Scope |
|---|---|---|
| M1 — Skeleton | ✅ done in this commit | FastAPI + Celery + Redis + SQLite + models + health check + upload page stub |
| M2 — Upload + extraction | ⏳ | PDF upload → text → chapter detection → chapter list |
| M3 — Audiobook end-to-end | ⏳ | Single-voice TTS through the whole pipeline |
| M4 — Podcast script generation | ⏳ | Gemini call → 2-host script (JSON, viewable in UI) |
| M5 — Two-voice TTS + assembly | ⏳ | Full podcast pipeline, per-segment TTS cache |
| M6 — Player + polish | ⏳ | Progress UI, error states, download, cleanup task |
