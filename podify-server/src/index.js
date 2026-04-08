require('dotenv').config();
const express = require('express');
const cors = require('cors');
const morgan = require('morgan');
const path = require('path');
const fs = require('fs');

const metadataRouter = require('../routes/metadata');
const extractRouter = require('../routes/extract');
const { authMiddleware } = require('../middleware/auth');

// ── Ensure tmp dir exists ──────────────────────────────────────────────────
const tmpDir = path.join(__dirname, '..', 'tmp');
if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });

// ── App setup ─────────────────────────────────────────────────────────────
const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(morgan('dev'));

// ── Health check (no auth needed) ─────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', version: '1.0.0', timestamp: new Date().toISOString() });
});

// ── Protected routes ───────────────────────────────────────────────────────
app.use('/metadata', authMiddleware);
app.use('/extract', authMiddleware);

app.use('/metadata', metadataRouter);
app.use('/extract', extractRouter);

// ── 404 handler ───────────────────────────────────────────────────────────
app.use((req, res) => {
  res.status(404).json({ error: 'Route not found' });
});

// ── Global error handler ──────────────────────────────────────────────────
app.use((err, req, res, next) => {
  console.error('[ERROR]', err.message);
  const status = err.status || 500;
  res.status(status).json({ error: err.message || 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`\n🎙  Podify server running on http://localhost:${PORT}`);
  console.log(`   POST /metadata  — fetch video info`);
  console.log(`   POST /extract   — extract audio\n`);
});