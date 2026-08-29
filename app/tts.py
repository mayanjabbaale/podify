"""TTS layer for Podify.

M3 scope: a single ``get_kokoro()`` singleton that loads the Kokoro
ONNX model + voices file once per process and reuses it across Celery
tasks. Synthesis is wrapped in a thin ``synthesize_text`` helper so
callers don't need to know about numpy / pydub internals.

The Kokoro package (``kokoro-onnx``) is loaded lazily on first call so
worker boot stays fast and tests that don't touch TTS don't pay the model
load cost. ``lru_cache`` keeps the instance alive for the worker's
lifetime.

M5 (podcast mode + per-segment cache) will add a per-text cache layer
in front of this module; for M3 every call is a fresh synthesis.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)


# Filenames the README instructs the user to drop into KOKORO_MODEL_DIR.
# Kept as constants so we can produce a precise FileNotFoundError if the
# user is missing one of them — much friendlier than the generic
# "session create failed" message Kokoro emits.
_MODEL_FILENAME = "kokoro-v1.0.onnx"
_VOICES_FILENAME = "voices-v1.0.bin"


def _model_paths() -> tuple[Path, Path]:
    """Return (model_path, voices_path) from settings, validating existence."""
    settings = get_settings()
    model_dir: Path = settings.kokoro_model_dir
    model_path = model_dir / _MODEL_FILENAME
    voices_path = model_dir / _VOICES_FILENAME

    missing = [str(p) for p in (model_path, voices_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Kokoro model files not found. Expected:\n  - "
            + "\n  - ".join(missing)
            + "\nDownload them from the "
            "'hexgrad/kokoro' 'model-files-v1.1' release on GitHub and "
            "place them in KOKORO_MODEL_DIR "
            f"({model_dir}). See README.md for details."
        )
    return model_path, voices_path


@lru_cache(maxsize=1)
def get_kokoro():
    """Return a process-wide Kokoro instance, constructing it on first call.

    ``lru_cache`` keeps one instance per Python process. Celery's solo
    pool runs one process, so this is the single model load per worker.
    Tests that need a fake Kokoro should ``monkeypatch`` this function
    (and call ``get_kokoro.cache_clear()`` so the patch isn't masked by
    a previously-cached real instance).

    We look up ``kokoro_onnx.Kokoro`` via module attribute (rather than
    ``from kokoro_onnx import Kokoro``) so tests can monkeypatch
    ``kokoro_onnx.Kokoro`` directly and have the patch observed here.
    """
    # Imported lazily so worker boot doesn't pay the onnxruntime cost
    # when no TTS task is ever run.
    import kokoro_onnx  # type: ignore[import-untyped]

    model_path, voices_path = _model_paths()
    logger.info("Loading Kokoro model from %s", model_path.parent)
    return kokoro_onnx.Kokoro(str(model_path), str(voices_path))


def reset_kokoro_cache() -> None:
    """Drop the cached Kokoro instance. Used by tests and (in the future)
    by a /admin endpoint that swaps model files on disk."""
    cache_clear = getattr(get_kokoro, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def synthesize_text(text: str, voice: str, speed: float = 1.0) -> tuple[np.ndarray, int]:
    """Synthesize ``text`` with the named Kokoro voice.

    Returns ``(samples, sample_rate)`` where ``samples`` is a 1-D
    ``np.float32`` array (mono) and ``sample_rate`` is 24000 Hz. Kokoro
    handles long-input chunking internally; we get back a single
    concatenated array.

    Raises ``ValueError`` if ``text`` is empty or whitespace-only — the
    caller should treat that as a job failure rather than a successful
    silence.
    """
    if not text or not text.strip():
        raise ValueError("Cannot synthesize empty text")

    kokoro = get_kokoro()
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed)

    # Defensive: Kokoro returns float32 mono at 24 kHz, but assert rather
    # than assume so a future Kokoro upgrade doesn't silently produce
    # wrong-shape audio that crashes pydub downstream.
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 1:
        raise ValueError(f"Kokoro returned non-mono audio with shape {samples.shape}")
    return samples, int(sample_rate)
