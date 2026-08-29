import pytest
from unittest.mock import MagicMock, patch
from app.scripting import generate_podcast_script

def test_generate_podcast_script_success():
    """Test successful script generation and parsing."""
    mock_response = MagicMock()
    mock_response.text = '[{"speaker": "host_a", "text": "Hello!"}, {"speaker": "host_b", "text": "Hi!"}]'

    with patch("app.scripting.client.models.generate_content", return_value=mock_response):
        with patch("app.scripting.settings") as mock_settings:
            mock_settings.gemini_api_key = "test_key"
            script = generate_podcast_script("Some chapter text.")

            assert len(script) == 2
            assert script[0]["speaker"] == "host_a"
            assert script[0]["text"] == "Hello!"
            assert script[1]["speaker"] == "host_b"
            assert script[1]["text"] == "Hi!"

def test_generate_podcast_script_markdown_fences():
    """Test that markdown fences are stripped correctly."""
    mock_response = MagicMock()
    mock_response.text = '```json\n[{"speaker": "host_a", "text": "Hello!"}]\n```'

    with patch("app.scripting.client.models.generate_content", return_value=mock_response):
        with patch("app.scripting.settings") as mock_settings:
            mock_settings.gemini_api_key = "test_key"
            script = generate_podcast_script("Some chapter text.")
            assert len(script) == 1
            assert script[0]["text"] == "Hello!"

def test_generate_podcast_script_invalid_json():
    """Test that invalid JSON raises ValueError."""
    mock_response = MagicMock()
    mock_response.text = 'Not JSON at all'

    with patch("app.scripting.client.models.generate_content", return_value=mock_response):
        with patch("app.scripting.settings") as mock_settings:
            mock_settings.gemini_api_key = "test_key"
            with pytest.raises(ValueError) as excinfo:
                generate_podcast_script("Some chapter text.")
            assert "Gemini returned invalid JSON" in str(excinfo.value)

def test_generate_podcast_script_invalid_structure():
    """Test that JSON with wrong structure raises ValueError."""
    mock_response = MagicMock()
    mock_response.text = '[{"wrong_key": "value"}]'

    with patch("app.scripting.client.models.generate_content", return_value=mock_response):
        with patch("app.scripting.settings") as mock_settings:
            mock_settings.gemini_api_key = "test_key"
            with pytest.raises(ValueError) as excinfo:
                generate_podcast_script("Some chapter text.")
            assert "missing required fields 'speaker' or 'text'" in str(excinfo.value)

def test_generate_podcast_script_invalid_speaker():
    """Test that invalid speaker names raise ValueError."""
    mock_response = MagicMock()
    mock_response.text = '[{"speaker": "host_c", "text": "Hello!"}]'

    with patch("app.scripting.client.models.generate_content", return_value=mock_response):
        with patch("app.scripting.settings") as mock_settings:
            mock_settings.gemini_api_key = "test_key"
            with pytest.raises(ValueError) as excinfo:
                generate_podcast_script("Some chapter text.")
            assert "has invalid speaker: host_c" in str(excinfo.value)
