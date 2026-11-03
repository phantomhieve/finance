"""Universal sanitization, extraction, normalization, and security auditing for LLM I/O."""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# ===========================================================================
# 1. PII and Security Regex Patterns
# ===========================================================================

# Credit / Debit Card: 13 to 19 digits with optional spaces or hyphens
CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,7}|\d{13,19})\b")

# Indian PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")

# Indian Aadhaar: 12 digits, often in 4-4-4 format
AADHAAR_PATTERN = re.compile(r"\b(?:\d{4}\s\d{4}\s\d{4}|\d{4}-\d{4}-\d{4})\b")

# Indian Mobile Phone: +91 or leading 6-9, followed by 9 digits
PHONE_PATTERN = re.compile(r"(?:\+91[\-\s]?)?[6789]\d{9}\b")

# Bank Account Numbers: 9-18 digits preceded by common account keywords
ACCOUNT_PATTERN = re.compile(
    r"(?i)\b(?:a/c|acct?|account|account\s*no\.?|a/c\s*no\.?)\s*(?:is|:)?\s*(\d{9,18})\b"
)

# OTP / Passwords / PINs: 4 to 8 digits preceded by OTP keywords
OTP_PATTERN = re.compile(
    r"(?i)\b(?:otp|one\s*time\s*password|pin|auth\s*code|verification\s*code|secret\s*code)\s*(?:is|:)?\s*(\d{4,8})\b"
)

# Email Addresses
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Secrets & API Keys
GEMINI_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z\-_]{30,40}")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{15,}")
GENERIC_API_KEY_PATTERN = re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{20,}|shakti-[A-Za-z0-9_-]{10,})\b")
SECRET_KV_PATTERN = re.compile(
    r'(?i)(["\']?(?:password|token|api_key|client_secret|secret|authorization)["\']?\s*[:=]\s*["\'])([^"\']{4,})(["\'])'
)

# Prompt Injection Markers
INJECTION_PATTERNS = [
    re.compile(r"(?i)\b(?:ignore\s+(?:all\s+)?previous\s+instructions|disregard\s+(?:all\s+)?prior\s+instructions)\b"),
    re.compile(r"(?i)\b(?:system\s*prompt|system\s*instruction|reveal\s+(?:your\s+)?prompt)\b"),
    re.compile(r"(?i)\b(?:you\s+are\s+now\s+in\s+developer\s+mode|dan\s+mode|jailbreak|unrestricted\s+mode)\b"),
    re.compile(r"(?i)\b(?:act\s+as\s+an\s+unfiltered|bypass\s+safety\s+filters?)\b"),
    re.compile(r"(?i)<\s*/?\s*(?:system|user_payload|untrusted_data|instructions)\b"),
]


# ===========================================================================
# 2. Privacy & PII Scrubbing
# ===========================================================================

def mask_pii(text: str, preserve_card_tail: bool = True) -> str:
    """Mask sensitive Personally Identifiable Information (PII) before sending to external LLMs.

    Redacts:
    - Credit/Debit cards (preserves last 4 digits by default for ledger matching)
    - Indian PAN (Permanent Account Number)
    - Indian Aadhaar
    - Indian Mobile numbers
    - Bank Account numbers
    - OTP / Verification PINs
    - Email addresses
    """
    if not text:
        return ""

    # 1. Mask Credit Cards
    def _mask_card(match: re.Match) -> str:
        s = match.group(0).replace(" ", "").replace("-", "")
        if preserve_card_tail and len(s) >= 4:
            return f"[CARD_...{s[-4:]}]"
        return "[CARD_REDACTED]"

    text = CARD_PATTERN.sub(_mask_card, text)

    # 2. Mask Bank Account Numbers
    text = ACCOUNT_PATTERN.sub(lambda m: m.group(0).replace(m.group(1), "[ACCOUNT_REDACTED]"), text)

    # 3. Mask Indian PAN
    text = PAN_PATTERN.sub("[PAN_REDACTED]", text)

    # 4. Mask Indian Aadhaar
    text = AADHAAR_PATTERN.sub("[AADHAAR_REDACTED]", text)

    # 5. Mask OTP / PIN
    text = OTP_PATTERN.sub(lambda m: m.group(0).replace(m.group(1), "[OTP_REDACTED]"), text)

    # 6. Mask Indian Mobile Phones
    text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)

    # 7. Mask Email Addresses
    text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)

    return text


# ===========================================================================
# 3. Prompt Injection Defense & Boundary Isolation
# ===========================================================================

def escape_xml_boundaries(text: str) -> str:
    """Escape angle brackets within untrusted user data to prevent tag breakout."""
    if not text:
        return ""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def wrap_user_payload(text: str, tag: str = "user_payload", nonce: str | None = None) -> str:
    """Wrap untrusted user data in isolated XML boundary tags with tag escaping.

    Prevents prompt injection by isolating untrusted strings from system instructions.
    """
    tag_name = f"{tag}_{nonce}" if nonce else tag
    escaped = escape_xml_boundaries(text)
    return (
        f"<{tag_name}>\n"
        f"{escaped}\n"
        f"</{tag_name}>"
    )


def detect_prompt_injection(text: str) -> bool:
    """Heuristic check for common adversarial prompt injection or jailbreak patterns."""
    if not text:
        return False
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return True
    return False


# ===========================================================================
# 4. Secret & Credential Redaction in Logs and Traces
# ===========================================================================

def mask_secrets(text: str) -> str:
    """Redact API keys, tokens, and authorization credentials from log messages and exception traces."""
    if not text:
        return ""
    text = GEMINI_KEY_PATTERN.sub("[GEMINI_KEY_REDACTED]", text)
    text = BEARER_TOKEN_PATTERN.sub("Bearer [TOKEN_REDACTED]", text)
    text = GENERIC_API_KEY_PATTERN.sub("[API_KEY_REDACTED]", text)
    text = SECRET_KV_PATTERN.sub(r"\1[REDACTED]\3", text)
    return text


# ===========================================================================
# 5. JSON Extraction & Cleaning
# ===========================================================================

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
