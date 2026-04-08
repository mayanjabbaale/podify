const express = require('express');
const router = express.Router();
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');
const { getMetadata, extractAudioFile } = require('../services/ytdlp');
const { uploadAudio } = require('../services/storage');

/**
 * POST /extract
 * Body: { url: string }
 *
 * Full pipeline:
 *   1. Validate URL & fetch metadata
 *   2. Download + extract audio with yt-dlp (saved to /tmp)
 *   3. Upload MP3 to Supabase Storage
 *   4. Delete local temp file
 *   5. Return episode data with public audioUrl
 *
 * This can take 10-60 seconds depending on video length.
 * The request stays open — consider a job queue (Step 8) for very long videos.
 *
 * Response:
 * {
 *   id, title, source, duration, durationLabel,
 *   fileSizeMb, thumbnailColor, thumbnailUrl, audioUrl
 * }
 */
router.post('/', async (req, res, next) => {
  const { url } = req.body;

  if (!url || typeof url !== 'string') {
    return res.status(400).json({ error: 'url is required' });
  }

  const extractionId = uuidv4();
  let localFilePath = null;

  console.log(`[EXTRACT] Starting extraction ${extractionId} for: ${url}`);

  try {
    // ── Step 1: Metadata ───────────────────────────────────────────────
    console.log(`[EXTRACT] ${extractionId} — fetching metadata`);
    const metadata = await getMetadata(url);

    // ── Step 2: Download audio ─────────────────────────────────────────
    console.log(`[EXTRACT] ${extractionId} — downloading audio for "${metadata.title}"`);
    localFilePath = await extractAudioFile(url, extractionId);

    const fileStat = fs.statSync(localFilePath);
    const actualFileSizeMb = Math.round(fileStat.size / 1024 / 1024);

    // ── Step 3: Upload to storage ──────────────────────────────────────
    const storageFileName = `${extractionId}.mp3`;
    console.log(`[EXTRACT] ${extractionId} — uploading to storage`);
    const audioUrl = await uploadAudio(localFilePath, storageFileName);

    // ── Step 4: Cleanup ────────────────────────────────────────────────
    fs.unlinkSync(localFilePath);
    localFilePath = null;
    console.log(`[EXTRACT] ${extractionId} — done ✓`);

    // ── Step 5: Respond ────────────────────────────────────────────────
    res.json({
      id: extractionId,
      title: metadata.title,
      source: metadata.source,
      duration: metadata.duration,
      durationLabel: metadata.durationLabel,
      fileSizeMb: actualFileSizeMb,
      thumbnailColor: metadata.thumbnailColor,
      thumbnailUrl: metadata.thumbnailUrl,
      audioUrl,
    });
  } catch (err) {
    // Always clean up temp file on failure
    if (localFilePath && fs.existsSync(localFilePath)) {
      fs.unlinkSync(localFilePath);
    }
    console.error(`[EXTRACT] ${extractionId} — failed:`, err.message);
    next(err);
  }
});

module.exports = router;