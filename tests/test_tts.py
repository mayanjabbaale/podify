"""Tests for app.tts — the Kokoro singleton and synthesize_text helper.

These tests intentionally do NOT load the real Kokoro model. The model
files live in ``storage/models/kokoro/`` and are not checked into the
repo; the lazy ``get_kokoro()`` raises ``FileNotFoundError`` with a
clear message if they're absent. The actual synthesis path is exercised
end-to-end in tests/test_jobs.py with a monkeypatched Kokoro so the
synthesize_audiobook task can run in CI without model files.
"""

from __future__ import annotations

import pytest

from app import tts


@pytest.fixture(autouse=True)
def _clear_kokoro_cache():
    """Each test starts with a clean lru_cache for get_kokoro()."""
    tts.reset_kokoro_cache()
    yield
    tts.reset_kokoro_cache()


def test_get_kokoro_raises_filenotfound_when_models_missing(tmp_path, monkeypatch) -> None:
    """No model files on disk -> clear error, not a cryptic stack trace."""
    from app.config import get_settings

    monkeypatch.setattr(
        get_settings(), "kokoro_model_dir", tmp_path, raising=False
    )
    with pytest.raises(FileNotFoundError) as excinfo:
        tts.get_kokoro()
    msg = str(excinfo.value)
    assert "kokoro-v1.0.onnx" in msg
    assert "voices-v1.0.bin" in msg


def test_synthesize_text_rejects_empty_input(monkeypatch) -> None:
    """Empty text fails fast with a clear ValueError — never silently returns silence."""
    # No need to actually call Kokoro for this — we exercise the guard.
    with pytest.raises(ValueError, match="empty"):
        tts.synthesize_text("", voice="af_nicole")
    with pytest.raises(ValueError, match="empty"):
        tts.synthesize_text("   \n\n  ", voice="af_nicole")


def test_synthesize_text_uses_singleton(monkeypatch) -> None:
    """Two calls return the same Kokoro instance — lru_cache works."""
    from app.config import get_settings

    fake_dir = get_settings().kokoro_model_dir
    # Drop a sentinel file pair so get_kokoro() can construct, then monkeypatch
    # the Kokoro class itself to avoid the onnxruntime import. The point of
    # this test is the lru_cache behavior, not real synthesis.
    (fake_dir).mkdir(parents=True, exist_ok=True)
    (fake_dir / "kokoro-v1.0.onnx").write_bytes(b"")
    (fake_dir / "voices-v1.0.bin").write_bytes(b"")

    class FakeKokoro:
        def __init__(self, *args, **kwargs):
            pass

        def create(self, text, voice, speed=1.0, **kwargs):
            import numpy as np

            return np.zeros(24000, dtype=np.float32), 24000

    # ``app.tts.get_kokoro()`` does ``from kokoro_onnx import Kokoro``
    # inside the function body, so we have to patch the class on its
    # source module, not on ``app.tts``.
    monkeypatch.setattr("kokoro_onnx.Kokoro", FakeKokoro)

    a = tts.synthesize_text("hello", voice="af_nicole")
    b = tts.synthesize_text("world", voice="af_nicole")
    assert a is not None
    assert b is not None
    # lru_cache guarantees the underlying instance is reused.
    assert tts.get_kokoro() is tts.get_kokoro()
