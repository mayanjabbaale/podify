// extractionService.js
// Talks to your Node.js backend.
//
// LOCAL DEV:  set BASE_URL to your machine's LAN IP (not localhost —
//             the phone can't resolve localhost on your computer).
//             Find your IP with `ipconfig` (Windows) or `ifconfig` (Mac/Linux).
//             Example: http://192.168.1.42:3000
//
// PRODUCTION: point BASE_URL to your deployed server URL.

import Constants from 'expo-constants';

// Pull the server URL from app.json extra config, or fall back to a default.
// To configure per-environment, set "extra": { "serverUrl": "..." } in app.json.
const BASE_URL =
  Constants.expoConfig?.extra?.serverUrl || 'http://192.168.1.100:3000';

// The shared secret must match API_SECRET in your server's .env file.
const API_SECRET =
  Constants.expoConfig?.extra?.apiSecret || 'replace-with-your-random-secret';

const HEADERS = {
  'Content-Type': 'application/json',
  'x-api-secret': API_SECRET,
};

/**
 * Fetches YouTube video metadata (title, duration, thumbnail, channel).
 * Fast — no media is downloaded on the server.
 */
export async function fetchVideoMetadata(youtubeUrl) {
  const res = await fetch(`${BASE_URL}/metadata`, {
    method: 'POST',
    headers: HEADERS,
    body: JSON.stringify({ url: youtubeUrl }),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || 'Failed to fetch video info');
  }

  return data;
}

/**
 * Triggers audio extraction on the backend.
 * The server downloads the audio, uploads to Supabase, and returns a public URL.
 * This can take 10–60 seconds — keep the request open.
 */
export async function extractAudio(youtubeUrl) {
  const res = await fetch(`${BASE_URL}/extract`, {
    method: 'POST',
    headers: HEADERS,
    body: JSON.stringify({ url: youtubeUrl }),
  });

  const data = await res.json();

  if (!res.ok) {
    throw new Error(data.error || 'Extraction failed');
  }

  return data;
}

/**
 * Validates that a string looks like a YouTube URL.
 * Client-side only — no network call.
 */
export function isValidYouTubeUrl(url) {
  return /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]{11}/.test(
    url?.trim()
  );
}

/**
 * Extracts the video ID from a YouTube URL.
 */
export function extractVideoId(url) {
  const match = url?.match(/(?:v=|youtu\.be\/)([\w-]{11})/);
  return match ? match[1] : null;
}

/**
 * Checks that the server is reachable.
 * Call this on app start to give an early error if misconfigured.
 */
export async function checkServerHealth() {
  try {
    const res = await fetch(`${BASE_URL}/health`, { method: 'GET' });
    return res.ok;
  } catch {
    return false;
  }
}