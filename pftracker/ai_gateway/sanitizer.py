"""Universal sanitization, extraction, and normalization for LLM output."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def clean_json_text(text: str) -> str:
    """Extract valid JSON from LLM output, stripping reasoning tags and markdown fences.

    Handles:
    - DeepSeek reasoning traces (<think>...</think> and unclosed <think>)
    - Markdown code fences (```json, ```)
    - Preamble and postamble commentary
    - Trailing commas before closing braces or brackets
    """
    if not text:
        return ""

    # 1. Strip <think>...</think> reasoning traces if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in text and "</think>" not in text:
        text = text.split("<think>", 1)[0]
    text = text.strip()

    # 2. Strip code block fences
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
        else:
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    # 3. Locate outer JSON object or array
    first_obj = text.find("{")
    first_arr = text.find("[")

    if first_obj != -1 and (first_arr == -1 or first_obj < first_arr):
        # Target is a JSON object
        last_obj = text.rfind("}")
        if last_obj != -1 and last_obj > first_obj:
            text = text[first_obj:last_obj + 1].strip()
    elif first_arr != -1:
        # Target is a JSON array
        last_arr = text.rfind("]")
        if last_arr != -1 and last_arr > first_arr:
            text = text[first_arr:last_arr + 1].strip()

    # 4. Clean trailing commas before } or ]
    text = re.sub(r",\s*([\]}])", r"\1", text)
    return text


def safe_json_loads(text: str) -> tuple[dict | list | None, str]:
    """Attempt direct JSON parsing, then clean and retry.

    Returns (parsed_data, cleaned_text).
    """
    text = text.strip()
    try:
        return json.loads(text), text
    except Exception:
        cleaned = clean_json_text(text)
        try:
            return json.loads(cleaned), cleaned
        except Exception as exc:
            logger.debug("Failed to parse JSON even after sanitization: %s", exc)
            return None, cleaned
