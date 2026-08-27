# Project Brief: PDF → Audiobook & Podcast Converter

## 1. Summary

A web app that takes a PDF book as input and produces two kinds of audio output:

1. **Audiobook mode** — single-narrator TTS reading of the extracted text, chaptered.
2. **Podcast mode** — an LLM rewrites a chapter into a two-host conversational script, rendered with two distinct TTS voices. **This is the priority for MVP.**

**Constraint: no cloud storage, no billing anywhere.** Storage, database, queue, and TTS all run on infrastructure you control. Script generation uses the **Gemini API free tier** (no credit card, no billing) rather than a paid API, chosen specifically to keep the local LLM's RAM footprint off an 8GB machine — see the hardware note in section 2 for why.

## 2. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Plain HTML + Tailwind CSS (CDN or build step, no React) | Server-rendered pages from FastAPI (Jinja2 templates) or a static HTML/JS app calling the API — pick one, see Open Decisions |
| Backend | Python, FastAPI | Async-friendly, best PDF/audio library ecosystem |
| Job queue | Redis + Celery (or RQ if we want something lighter) | Self-hosted, free. TTS/script generation take minutes — must run as background jobs, never inline in a request |
| Database | **SQLite** (or Postgres if hardware allows) | Books, chapters, jobs, generated episodes. SQLite has near-zero memory overhead, a real advantage on constrained hardware — see hardware note below |
| File storage | Local filesystem (e.g. `./storage/pdfs`, `./storage/audio`) | No S3/cloud bucket. Fine for single-server MVP; revisit only if we outgrow one machine |
| Script generation LLM | **Gemini API (free tier)** — e.g. `gemini-2.5-flash` | No credit card required, generous free quota (1,500 requests/day, 15 RPM, 1M TPM as of mid-2026 — plenty for a single-user MVP). Removes the LLM's RAM footprint from your machine entirely, which matters a lot on 8GB. **Never enable billing on this project** — doing so deletes the free tier and makes every call billable from the first token. Trade-off: chapter text leaves your machine and Google may use free-tier traffic to improve its models — a local Ollama model (3B-4B class, see note below) remains the fallback if that's a dealbreaker |
| TTS | **Kokoro-82M** (Apache 2.0, local, CPU-friendly, 54 voices) | Runs locally via `pip install kokoro`. For podcast mode, assign two different Kokoro voices to the two hosts and synthesize each turn separately; for audiobook mode, one voice for the whole chapter |
| PDF parsing | PyMuPDF (`fitz`) | Text extraction + basic layout detection for chapter breaks |
| Audio assembly | `pydub` (+ ffmpeg) | Stitch TTS clips, normalize levels, add intro/outro |

**Why Kokoro:** it's Apache-2.0 licensed (free for commercial use), ~327MB, runs fast even on CPU with no GPU required, and ships 54 voices — enough to give each podcast host a distinct, consistent voice without needing a true multi-speaker model or any paid cloning service. If voice quality needs to go up later, Chatterbox (MIT-licensed, also local) is a drop-in upgrade path — keep the TTS layer behind an interface so swapping is cheap.

**Why Gemini free tier over a local LLM:** on 8GB RAM, removing the LLM from your machine entirely is the single biggest memory win available — Kokoro's ~2-3GB footprint alongside Postgres/SQLite, Redis, and the app itself is comfortable; adding a 3-4B local model on top of that is not. The free tier requires no billing and no credit card, so it doesn't violate the no-billing constraint. The one thing to watch: never add a billing method to the Google Cloud project holding this API key — Gemini deletes the free tier entirely the moment billing is enabled on a project, turning every call billable from token one. If keeping book content fully offline matters more than the RAM headroom, fall back to a local Ollama model in the 3B-4B class (Llama 3.2 3B, Qwen3 4B, Phi-4 Mini, or Gemma 3 4B) — see hardware note below for why that size ceiling exists on this hardware.

**Hardware note (8GB RAM target):** 8GB is *total system RAM*, shared by the OS, Postgres/SQLite, Redis, the app itself, and — if using the local-LLM fallback — whatever's loaded in Ollama. At Q4 quantization, a 7-8B model needs ~5-6GB just for weights + KV cache, which leaves too little headroom on an 8GB machine and will thrash or swap under load. If you do go local, stay in the **3B-4B parameter class** (roughly 2-3.5GB at Q4). Using Gemini's free tier instead sidesteps this constraint entirely, which is why it's the primary recommendation on this hardware. Kokoro's ~2-3GB footprint fits comfortably either way. If Postgres' overhead matters at this RAM budget, SQLite is a lighter-weight substitute for the MVP (see table above).

## 3. Pipeline

```
Upload PDF
   │
   ▼
1. Extract & clean text (strip headers/footers/page numbers)
   │
   ▼
2. Detect chapter boundaries → store as Chapter records
   │
   ▼
3. User picks a chapter + mode (audiobook | podcast)
   │
   ▼
4a. AUDIOBOOK: chunk text → single Kokoro voice → TTS per chunk
4b. PODCAST: chapter text → Gemini API (free tier) generates 2-host script →
    each turn synthesized with that host's assigned Kokoro voice
   │
   ▼
5. Assemble: stitch clips in order (pydub), normalize audio, add intro/outro bed
   │
   ▼
6. Save final file to local storage, mark Job as complete
   │
   ▼
7. Frontend polls job status → shows player + download link
```

Every step from 3 onward runs as a Celery task chain, not inline in an HTTP handler. The frontend uploads, gets a `job_id`, and polls a status endpoint.

## 4. Data Model (draft)

```
Book
  id, title, original_filename, storage_path, uploaded_at, status

Chapter
  id, book_id, index, title, raw_text, cleaned_text, char_count

Job
  id, chapter_id, mode ("audiobook" | "podcast"), status
      ("queued" | "extracting" | "scripting" | "synthesizing" | "assembling" | "done" | "failed")
  progress_pct, error_message, created_at, completed_at

Episode
  id, job_id, storage_path, duration_seconds, format ("mp3" | "wav"), created_at

PodcastScript          # only for podcast mode, useful for debugging/regeneration
  id, job_id, turns (JSON: [{speaker: "host_a"|"host_b", voice: "af_bella"|"am_adam", text: "..."}])
```

`storage_path` is a path on local disk, not a cloud key.

## 5. API Endpoints (draft)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/books` | Upload a PDF, kicks off extraction + chapter detection |
| GET | `/api/books/{id}` | Book detail incl. chapter list |
| POST | `/api/books/{id}/chapters/{chapter_id}/jobs` | Start a generation job (`mode` in body) |
| GET | `/api/jobs/{id}` | Poll job status/progress |
| GET | `/api/episodes/{id}` | Episode metadata + playback URL |
| GET | `/api/episodes/{id}/audio` | Stream the local audio file (FastAPI `FileResponse`) |

## 6. Frontend Pages (HTML + Tailwind, no framework)

1. **Upload page** — drag/drop or file picker, upload progress bar
2. **Book detail page** — chapter list with char counts, "Generate Podcast" / "Generate Audiobook" buttons per chapter
3. **Job status page** — polls `/api/jobs/{id}`, shows a progress bar with the current stage (extracting → scripting → synthesizing → assembling)
4. **Player page** — `<audio>` element, download link, basic metadata (chapter title, duration, mode)

Keep all state on the server / in the URL where possible (job id in the path) so pages work with plain `fetch()` polling and no client-side framework or router.

## 7. Environment Variables

```
DATABASE_URL=sqlite:///./storage/app.db
REDIS_URL=redis://localhost:6379/0
STORAGE_DIR=./storage
GEMINI_API_KEY=               # free-tier key from Google AI Studio, no credit card
# --- Optional: only if using the fully-local fallback instead of Gemini ---
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

No paid API keys required. `GEMINI_API_KEY` is a free-tier key from Google AI Studio (no credit card) — everything else above points at local services.

## 8. Local Services Setup (what needs to run on the machine)

- **SQLite** — no separate service, just a file; use Postgres instead only if hardware/scale later justifies it
- **Redis** — Docker container or native install
- **Gemini API key** — free, from Google AI Studio, no credit card. (Skip Ollama entirely unless using the fully-local fallback.)
- **Ollama** *(optional fallback only)* — if choosing to keep script generation fully local instead of using Gemini's free tier, install natively and pull a 3B-4B model (`ollama pull llama3.2:3b`)
- **Kokoro** — installed as a Python package (`pip install kokoro soundfile`, plus the `espeak-ng` system package it depends on)
- **ffmpeg** — system package, required by `pydub`

A `docker-compose.yml` for Postgres + Redis (with Ollama and the FastAPI/Celery app running natively or also containerized) is a reasonable first thing to build.

## 9. Build Order (suggested milestones)

1. **Skeleton**: FastAPI app, Postgres models + migrations, Celery worker wired to Redis, health check endpoint
2. **Upload + extraction**: PDF upload → text extraction → chapter detection, stored in DB and on local disk, visible on a plain HTML page
3. **Audiobook path end-to-end** (simpler than podcast — good for validating the whole async job + local storage + player flow, and for confirming Kokoro's setup works, before adding script generation)
4. **Podcast script generation**: Gemini API call that turns one chapter into a 2-host script, stored and viewable as JSON/text before wiring TTS
5. **Two-voice TTS + assembly** for podcast mode
6. **Player + polish**: progress UI, error states, download

Each milestone should be independently demoable.

## 10. Non-Goals for v1

- Voice cloning
- RSS feed publishing / podcast platform distribution
- Multi-book libraries / user accounts beyond basic auth
- Whole-book generation in one job (start with single chapter)
- Fine-grained voice/style controls in the UI (hardcode good defaults first)
- Any cloud deployment of the app itself — storage, DB, queue, and TTS all stay local. (Script generation already uses the Gemini cloud API free tier by design; that's the single cloud dependency.)

## 11. Open Decisions (need a call before/while building)

- **Rendering approach**: server-rendered Jinja2 templates from FastAPI, or a static HTML/JS frontend that only talks to the API? (Affects deployment shape.)
- **Hardware target**: confirmed 8GB system RAM, no GPU assumed — using Gemini's free tier for script generation instead of a local model reflects this constraint. Revisit if a GPU/more RAM becomes available and fully-local is preferred.
- **Local vs. hosted script generation**: Gemini free tier (recommended, frees up RAM, needs internet + sends text to Google) vs. local Ollama 3B-4B model (fully offline, weaker output, tighter on 8GB). Worth deciding explicitly rather than defaulting.
- **Auth model**: none for MVP (single-user/local tool), or basic email+password if this needs to serve more than one person?
- **Chapter detection accuracy**: PDFs vary wildly in structure — worth deciding an acceptable fallback (e.g., fixed-length chunks) if heading detection fails, rather than blocking on perfect chapter parsing.
- **Local LLM model choice** *(only relevant if using the offline fallback instead of Gemini)*: pick and pin one (Llama 3.2 3B, Qwen3 4B, Phi-4 Mini, or Gemma 3 4B) after a quick side-by-side test on the actual script-generation prompt — conversational quality varies more than benchmark scores suggest, and at this size the gap between models can be significant.