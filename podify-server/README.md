# Podify Server

Node.js backend for the Podify app. Extracts audio from YouTube videos using `yt-dlp` and stores the MP3s in Supabase Storage.

---

## Prerequisites

### 1. Install yt-dlp

yt-dlp is the tool that actually downloads the audio. Install it globally:

**macOS (Homebrew):**
```bash
brew install yt-dlp
```

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install yt-dlp
```

**Windows:**
```bash
winget install yt-dlp
# or download yt-dlp.exe from https://github.com/yt-dlp/yt-dlp/releases
```

Verify it works:
```bash
yt-dlp --version
```

### 2. Set up Supabase Storage

1. Go to https://supabase.com and create a free project
2. In your project, go to **Storage** → **New bucket**
3. Name it `podify-audio`
4. Set it to **Public** (so the app can stream audio directly)
5. Go to **Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role key** (under Secret) → `SUPABASE_SERVICE_KEY`

---

## Setup

```bash
# 1. Clone / navigate to the server folder
cd podify-server

# 2. Install dependencies
npm install

# 3. Copy the env template
cp .env.example .env

# 4. Edit .env with your values
nano .env   # or open in your editor
```

Your `.env` should look like:
```
PORT=3000
SUPABASE_URL=https://abcdefghij.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGci...your-service-role-key
SUPABASE_BUCKET=podify-audio
API_SECRET=your-random-secret-here
MAX_DURATION_SECONDS=10800
```

Generate a random API secret:
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

---

## Running

```bash
# Development (auto-restarts on file changes — Node 18+)
npm run dev

# Production
npm start
```

You should see:
```
🎙  Podify server running on http://localhost:3000
   POST /metadata  — fetch video info
   POST /extract   — extract audio
```

---

## Connecting your phone to the server

Your phone and computer must be on the **same Wi-Fi network**.

1. Find your computer's local IP:
   - **Mac/Linux:** `ifconfig | grep "inet " | grep -v 127`
   - **Windows:** `ipconfig` → look for IPv4 Address

2. Update `app.json` in the React Native project:
```json
"extra": {
  "serverUrl": "http://YOUR_LOCAL_IP:3000",
  "apiSecret": "your-random-secret-here"
}
```

3. Test the connection from your browser or Postman:
```
GET http://YOUR_LOCAL_IP:3000/health
```

---

## API Reference

### `GET /health`
No auth required. Returns server status.

```json
{ "status": "ok", "version": "1.0.0", "timestamp": "..." }
```

---

### `POST /metadata`
Returns video info without downloading anything. Fast (~1-2s).

**Headers:** `x-api-secret: your-secret`

**Body:**
```json
{ "url": "https://youtube.com/watch?v=dQw4w9WgXcQ" }
```

**Response:**
```json
{
  "videoId": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "source": "Rick Astley",
  "duration": 212,
  "durationLabel": "3m",
  "fileSizeMb": 3,
  "thumbnailColor": ["#1a3a2a", "#2d6a4f"],
  "thumbnailUrl": "https://..."
}
```

---

### `POST /extract`
Full extraction pipeline. Takes 10–60s depending on video length.

**Headers:** `x-api-secret: your-secret`

**Body:**
```json
{ "url": "https://youtube.com/watch?v=dQw4w9WgXcQ" }
```

**Response:**
```json
{
  "id": "uuid",
  "title": "...",
  "source": "...",
  "duration": 212,
  "durationLabel": "3m",
  "fileSizeMb": 3,
  "thumbnailColor": ["#1a3a2a", "#2d6a4f"],
  "thumbnailUrl": "https://...",
  "audioUrl": "https://your-project.supabase.co/storage/v1/object/public/podify-audio/uuid.mp3"
}
```

---

## Error responses

All errors return:
```json
{ "error": "Human-readable message" }
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request (invalid URL, missing body) |
| 401 | Missing API secret header |
| 403 | Wrong API secret, or private video |
| 404 | Video not found / removed |
| 422 | Video too long |
| 502 | yt-dlp or storage upstream error |
| 500 | Unexpected server error |

---

## Legal note

This server uses `yt-dlp` which technically violates YouTube's Terms of Service for non-personal use. For a hobby project this is fine. Before going commercial, research alternatives:
- **YouTube Data API v3** (metadata only, no audio)
- Licensed audio APIs
- Targeting only Creative Commons licensed content