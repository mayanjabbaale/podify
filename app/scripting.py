"""Podcast script generation using Gemini API.
This module handles the transformation of raw chapter text into a two-host conversational script.
"""

import json
import logging
from typing import Any

from google import genai
from app.config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
settings = get_settings()

# Configure the Gemini client
client = genai.Client(api_key=settings.gemini_api_key)
model_id = "gemini-2.0-flash"

SYSTEM_PROMPT = """
You are an expert podcast scriptwriter. Your task is to rewrite the provided book chapter text into a natural, engaging, two-host conversational podcast script.

The goal is to make the content accessible and entertaining while preserving the core ideas, nuance, and key arguments of the text.

GUIDELINES:
1. HOSTS: There are two hosts, Host A and Host B.
   - Host A: The lead narrator/interviewer. Sets the stage, guides the conversation, and asks probing questions.
   - Host B: The expert/commentator. Explains the complex concepts, provides examples, and adds depth.
2. TONE: Conversational, intellectual but accessible. Use natural spoken language (contractions, "you know", "right", "basically").
3. STRUCTURE:
   - Intro: Start with a brief, hooky opening that introduces the chapter's main theme.
   - Body: Break the text into logical segments. Each segment should be a back-and-forth conversation.
   - Outro: Summarize the key takeaway and end with a satisfying closing statement.
4. PACING: Vary the length of turns. Some should be short reactions ("Exactly!", "Right"), others should be longer explanations.
5. ACCURACY: Do not hallucinate facts. Only use the information provided in the text. If the text is unclear, the hosts should discuss that ambiguity rather than inventing an answer.

OUTPUT FORMAT:
You MUST return the script as a JSON array of objects. Each object must have:
- "speaker": Either "host_a" or "host_b"
- "text": The spoken text for that turn.

Example:
[
  {"speaker": "host_a", "text": "Welcome back! Today we're diving into the second chapter of..."},
  {"speaker": "host_b", "text": "Yeah, this part is actually where things get really interesting because..."},
  {"speaker": "host_a", "text": "Wait, really? I didn't realize that was the case."},
  {"speaker": "host_b", "text": "Exactly! The author argues that..."}
]

Do not include any markdown formatting (like ```json) in your response. Return ONLY the raw JSON array.
"""

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
)
def generate_podcast_script(text: str) -> list[dict[str, str]]:
    """
    Calls Gemini API to generate a podcast script from the provided text.

    Args:
        text: The cleaned text of the book chapter.

    Returns:
        A list of turn dictionaries containing 'speaker' and 'text'.

    Raises:
        ValueError: If the API response cannot be parsed as JSON.
        Exception: For API-related failures (handled by @retry).
    """
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured in environment.")

    prompt = f"{SYSTEM_PROMPT}\n\nBOOK CHAPTER TEXT:\n\n{text}"

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
        )
        response_text = response.text.strip()

        # Basic cleaning in case the model ignores instructions and adds markdown fences
        if response_text.startswith("```"):
            # Remove opening and closing fences
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()

        try:
            script = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from Gemini response: {e}")
            raise ValueError(f"Gemini returned invalid JSON: {response_text[:200]}...") from e

        if not isinstance(script, list):
            raise ValueError(f"Expected a JSON list from Gemini, got {type(script)}")

        # Validate turn structure
        for i, turn in enumerate(script):
            if not isinstance(turn, dict) or "speaker" not in turn or "text" not in turn:
                raise ValueError(f"Turn {i} is missing required fields 'speaker' or 'text'")
            if turn["speaker"] not in ("host_a", "host_b"):
                raise ValueError(f"Turn {i} has invalid speaker: {turn['speaker']}")

        return script

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.exception(f"Unexpected error calling Gemini API: {e}")
        raise
