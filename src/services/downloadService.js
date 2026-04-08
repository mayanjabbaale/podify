// downloadService.js
// Manages downloading audio files to device storage using expo-file-system.
// Downloads survive app restarts. Local files are preferred over remote URLs
// by audioService so episodes play without internet once downloaded.

import * as FileSystem from 'expo-file-system/legacy';

const DOWNLOAD_DIR = `${FileSystem.documentDirectory}podify/`;

// ── In-memory download state ──────────────────────────────────────────────────
// episodeId → { progress: 0–1, status: 'downloading'|'done'|'error', resumable }
const _downloads = new Map();
const _listeners = new Set();

function _notify() {
  const snapshot = Object.fromEntries(_downloads);
  _listeners.forEach((fn) => fn(snapshot));
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Subscribe to download state changes.
 * Returns an unsubscribe function.
 */
export function subscribeDownloads(listener) {
  _listeners.add(listener);
  listener(Object.fromEntries(_downloads)); // immediate snapshot
  return () => _listeners.delete(listener);
}

export function getDownloadState(episodeId) {
  return _downloads.get(episodeId) || null;
}

/**
 * Ensure the downloads directory exists.
 * Call once on app start.
 */
export async function initDownloads() {
  const info = await FileSystem.getInfoAsync(DOWNLOAD_DIR);
  if (!info.exists) {
    await FileSystem.makeDirectoryAsync(DOWNLOAD_DIR, { intermediates: true });
  }
}

/**
 * Returns the local file path for an episode if it exists on disk.
 * Returns null if not downloaded.
 */
export async function getLocalPath(episodeId) {
  const path = `${DOWNLOAD_DIR}${episodeId}.mp3`;
  const info = await FileSystem.getInfoAsync(path);
  return info.exists ? path : null;
}

/**
 * Synchronously returns the expected local path (without checking disk).
 * Use for fast UI checks when you know the file should be there.
 */
export function localPathFor(episodeId) {
  return `${DOWNLOAD_DIR}${episodeId}.mp3`;
}

/**
 * Download an episode's audio to device storage.
 * Calls onProgress(0–1) as download proceeds.
 * Calls onComplete(localPath) when done.
 * Calls onError(message) on failure.
 */
export async function downloadEpisode({ episodeId, audioUrl, onProgress, onComplete, onError }) {
  if (!audioUrl) {
    onError?.('No audio URL to download');
    return;
  }

  const destPath = `${DOWNLOAD_DIR}${episodeId}.mp3`;

  // Already exists — don't re-download
  const existing = await FileSystem.getInfoAsync(destPath);
  if (existing.exists) {
    _downloads.set(episodeId, { progress: 1, status: 'done' });
    _notify();
    onComplete?.(destPath);
    return;
  }

  _downloads.set(episodeId, { progress: 0, status: 'downloading', resumable: null });
  _notify();

  const callback = (downloadProgress) => {
    const { totalBytesWritten, totalBytesExpectedToWrite } = downloadProgress;
    const progress =
      totalBytesExpectedToWrite > 0
        ? totalBytesWritten / totalBytesExpectedToWrite
        : 0;
    _downloads.set(episodeId, {
      ..._downloads.get(episodeId),
      progress,
    });
    _notify();
    onProgress?.(progress);
  };

  const resumable = FileSystem.createDownloadResumable(audioUrl, destPath, {}, callback);

  // Store resumable so we can cancel/pause it
  _downloads.set(episodeId, { progress: 0, status: 'downloading', resumable });
  _notify();

  try {
    const result = await resumable.downloadAsync();

    if (!result?.uri) throw new Error('Download returned no URI');

    _downloads.set(episodeId, { progress: 1, status: 'done', resumable: null });
    _notify();
    onComplete?.(result.uri);
  } catch (err) {
    // Cancelled downloads throw — distinguish from real errors
    const cancelled = err.message?.includes('cancelled') || err.message?.includes('aborted');
    _downloads.set(episodeId, {
      progress: 0,
      status: cancelled ? 'idle' : 'error',
      resumable: null,
    });
    _notify();
    if (!cancelled) onError?.(err.message);
  }
}

/**
 * Cancel an in-progress download.
 */
export async function cancelDownload(episodeId) {
  const state = _downloads.get(episodeId);
  if (state?.resumable) {
    try { await state.resumable.cancelAsync(); } catch {}
  }
  _downloads.delete(episodeId);
  _notify();
}

/**
 * Delete a downloaded file from device storage.
 */
export async function deleteDownload(episodeId) {
  const path = `${DOWNLOAD_DIR}${episodeId}.mp3`;
  try {
    const info = await FileSystem.getInfoAsync(path);
    if (info.exists) await FileSystem.deleteAsync(path);
  } catch {}
  _downloads.delete(episodeId);
  _notify();
}

/**
 * Returns total size of all downloaded files in MB.
 */
export async function getDownloadedSizeMb() {
  try {
    const info = await FileSystem.getInfoAsync(DOWNLOAD_DIR, { size: true });
    return Math.round((info.size || 0) / 1024 / 1024);
  } catch {
    return 0;
  }
}