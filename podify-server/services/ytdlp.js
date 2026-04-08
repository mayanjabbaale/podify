const { execFile } = require('child_process');
const { promisify } = require('util');
const path = require('path');
const fs = require('fs');

const execFileAsync = promisify(execFile);
const TMP_DIR = path.join(__dirname, '..', '..', 'tmp');
const MAX_DURATION = parseInt(process.env.MAX_DURATION_SECONDS || '10800', 10);

// ── Helpers ───────────────────────────────────────────────────────────────

function secondsToLabel(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function thumbnailColorFromId(videoId) {
  // Deterministically generate a gradient pair from the video ID
  const palettes = [
    ['#1a3a2a', '#2d6a4f'],
    ['#2a1a3a', '#4f2d6a'],
    ['#3a2a1a', '#6a4f2d'],
    ['#1a2a3a', '#2d4f6a'],
    ['#3a1a2a', '#6a2d4f'],
    ['#1a3a3a', '#2d6a6a'],
    ['#3a1a1a', '#6a2d2d'],
    ['#2a3a1a', '#4f6a2d'],
  ];
  const idx = videoId
    ? videoId.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % palettes.length
    : 0;
  return palettes[idx];
}

/**
 * Validates a YouTube URL format.
 * Does NOT hit YouTube — just regex checks.
 */
function isValidYouTubeUrl(url) {
  return /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/watch\?v=|youtu\.be\/)[\w-]{11}/.test(
    url?.trim()
  );
}

/**
 * Extracts the video ID from a YouTube URL.
 */
function extractVideoId(url) {
  const match = url.match(/(?:v=|youtu\.be\/)([\w-]{11})/);
  return match ? match[1] : null;
}

// ── Core yt-dlp functions ─────────────────────────────────────────────────

/**
 * Fetches video metadata using yt-dlp --dump-json.
 * Fast — does not download any media.
 */
async function getMetadata(youtubeUrl) {
  if (!isValidYouTubeUrl(youtubeUrl)) {
    throw Object.assign(new Error('Invalid YouTube URL'), { status: 400 });
  }

  let stdout;
  try {
    ({ stdout } = await execFileAsync('yt-dlp', [
      '--dump-json',
      '--no-playlist',
      '--no-warnings',
      youtubeUrl.trim(),
    ]));
  } catch (err) {
    // yt-dlp exits non-zero for unavailable/private videos
    const msg = err.stderr || err.message || '';
    if (msg.includes('Private video') || msg.includes('This video is private')) {
      throw Object.assign(new Error('This video is private'), { status: 403 });
    }
    if (msg.includes('not available') || msg.includes('removed')) {
      throw Object.assign(new Error('Video is unavailable'), { status: 404 });
    }
    throw Object.assign(new Error('Could not fetch video info'), { status: 502 });
  }

  const info = JSON.parse(stdout);

  if (info.duration > MAX_DURATION) {
    throw Object.assign(
      new Error(`Video is too long (max ${secondsToLabel(MAX_DURATION)})`),
      { status: 422 }
    );
  }

  const videoId = extractVideoId(youtubeUrl);

  return {
    videoId,
    title: info.title,
    source: info.uploader || info.channel || 'Unknown',
    duration: info.duration,
    durationLabel: secondsToLabel(info.duration),
    fileSizeMb: Math.round((info.duration * 16) / 1000 / 8), // rough estimate at 128kbps
    thumbnailColor: thumbnailColorFromId(videoId),
    thumbnailUrl: info.thumbnail,
  };
}

/**
 * Downloads and extracts audio from a YouTube video.
 * Returns the local file path of the extracted MP3.
 * Caller is responsible for cleaning up the file.
 */
async function extractAudioFile(youtubeUrl, outputId) {
  if (!isValidYouTubeUrl(youtubeUrl)) {
    throw Object.assign(new Error('Invalid YouTube URL'), { status: 400 });
  }

  const outputPath = path.join(TMP_DIR, `${outputId}.mp3`);

  try {
    await execFileAsync('yt-dlp', [
      '--extract-audio',
      '--audio-format', 'mp3',
      '--audio-quality', '5',        // ~128kbps — good quality, reasonable file size
      '--no-playlist',
      '--no-warnings',
      '--output', outputPath,
      youtubeUrl.trim(),
    ]);
  } catch (err) {
    // Clean up any partial file
    if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath);

    const msg = err.stderr || err.message || '';
    if (msg.includes('Private video')) {
      throw Object.assign(new Error('This video is private'), { status: 403 });
    }
    if (msg.includes('not available')) {
      throw Object.assign(new Error('Video is unavailable'), { status: 404 });
    }
    throw Object.assign(new Error('Audio extraction failed'), { status: 502 });
  }

  if (!fs.existsSync(outputPath)) {
    throw Object.assign(new Error('Extraction produced no output file'), { status: 500 });
  }

  return outputPath;
}

module.exports = { getMetadata, extractAudioFile, isValidYouTubeUrl };