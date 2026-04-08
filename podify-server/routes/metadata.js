const express = require('express');
const router = express.Router();
const { getMetadata } = require('../services/ytdlp');

/**
 * POST /metadata
 * Body: { url: string }
 *
 * Returns video metadata without downloading anything.
 * Fast — typically 1-2 seconds.
 *
 * Response:
 * {
 *   videoId, title, source, duration, durationLabel,
 *   fileSizeMb, thumbnailColor, thumbnailUrl
 * }
 */
router.post('/', async (req, res, next) => {
  const { url } = req.body;

  if (!url || typeof url !== 'string') {
    return res.status(400).json({ error: 'url is required' });
  }

  try {
    const metadata = await getMetadata(url);
    res.json(metadata);
  } catch (err) {
    next(err);
  }
});

module.exports = router;