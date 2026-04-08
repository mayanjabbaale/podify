// audioService.js
//
// A singleton that owns the expo-audio player and exposes it to the whole app.
// This solves two problems:
//   1. MiniPlayer needs live position without being inside PlayerScreen
//   2. Lock screen / Now Playing controls need a stable player reference
//
// Pattern: create the player once at module level, export helpers.
// Components call useAudioService() to get reactive state via a simple
// event-emitter + useState pattern — no context provider needed.

import { AudioPlayer, setAudioModeAsync } from 'expo-audio';

// ── Singleton player instance ─────────────────────────────────────────────────
let _player = null;
let _currentUri = null;

// ── Listeners for reactive updates ───────────────────────────────────────────
const _listeners = new Set();

function _notify(state) {
  _listeners.forEach((fn) => fn(state));
}

// ── Internal state ────────────────────────────────────────────────────────────
let _state = {
  isPlaying: false,
  position: 0,       // seconds
  duration: 0,       // seconds
  isLoaded: false,
  isBuffering: false,
  currentUri: null,
};

function _setState(patch) {
  _state = { ..._state, ...patch };
  _notify(_state);
}

// ── Polling interval (replaces status callbacks) ──────────────────────────────
// expo-audio's useAudioPlayerStatus hook can't be used outside React.
// We poll the player at 500ms for position updates — enough for a smooth
// MiniPlayer progress bar without hammering the JS thread.
let _pollInterval = null;

function _startPolling() {
  if (_pollInterval) return;
  _pollInterval = setInterval(() => {
    if (!_player) return;
    _setState({
      position: _player.currentTime ?? 0,
      duration: _player.duration ?? _state.duration,
      isPlaying: _player.playing ?? _state.isPlaying,
    });
  }, 500);
}

function _stopPolling() {
  if (_pollInterval) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Call once on app start to configure audio session.
 */
export async function initAudio() {
  try {
    await setAudioModeAsync({
      playsInSilentModeIOS: true,
      staysActiveInBackground: true,
      // These enable Now Playing / lock screen controls on iOS
      allowsRecordingIOS: false,
      interruptionModeIOS: 1, // DO_NOT_MIX
      shouldDuckAndroid: true,
      interruptionModeAndroid: 1,
      playThroughEarpieceAndroid: false,
    });
  } catch (e) {
    console.warn('[AudioService] setAudioModeAsync failed:', e.message);
  }
}

/**
 * Load and play a URI. Pass localPath to prefer the local file over the remote URL.
 * If the same URI is already loaded, just play from current position.
 */
export async function loadAndPlay(uri, startPositionSeconds = 0, localPath = null) {
  // Prefer local file — plays offline, no buffering
  const resolvedUri = localPath || uri;
  if (!resolvedUri) return;

  // Same track already loaded — just seek and play
  if (_player && _currentUri === resolvedUri) {
    if (startPositionSeconds > 0) _player.seekTo(startPositionSeconds);
    _player.play();
    _setState({ isPlaying: true });
    _startPolling();
    return;
  }

  // New track — tear down old player
  if (_player) {
    _player.remove();
    _player = null;
  }

  _currentUri = resolvedUri;
  _setState({ isLoaded: false, isBuffering: true, position: startPositionSeconds, currentUri: resolvedUri });

  try {
    _player = new AudioPlayer({ uri: resolvedUri });

    // Wait for loaded
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Load timeout')), 15000);
      const check = setInterval(() => {
        if (_player?.duration > 0) {
          clearInterval(check);
          clearTimeout(timeout);
          resolve();
        }
      }, 100);
    });

    if (startPositionSeconds > 0) _player.seekTo(startPositionSeconds);
    _player.play();

    _setState({
      isLoaded: true,
      isBuffering: false,
      isPlaying: true,
      duration: _player.duration,
      position: startPositionSeconds,
    });

    _startPolling();
  } catch (err) {
    console.error('[AudioService] loadAndPlay failed:', err.message);
    _setState({ isLoaded: false, isBuffering: false, isPlaying: false });
  }
}

export function play() {
  if (!_player) return;
  _player.play();
  _setState({ isPlaying: true });
  _startPolling();
}

export function pause() {
  if (!_player) return;
  _player.pause();
  _setState({ isPlaying: false });
}

export function seekTo(seconds) {
  if (!_player) return;
  _player.seekTo(seconds);
  _setState({ position: seconds });
}

export function setRate(rate) {
  if (!_player) return;
  _player.setPlaybackRate(rate);
}

export function getCurrentState() {
  return _state;
}

export function getPlayer() {
  return _player;
}

/**
 * Subscribe to state changes. Returns an unsubscribe function.
 * Used by useAudioService() hook and MiniPlayer.
 */
export function subscribe(listener) {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

export function teardown() {
  _stopPolling();
  if (_player) {
    _player.remove();
    _player = null;
  }
  _currentUri = null;
  _setState({ isPlaying: false, isLoaded: false, position: 0 });
}