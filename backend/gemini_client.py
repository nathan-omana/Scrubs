"""
The ONLY code that sends anything to Gemini. It only ever receives pseudonymized text.
"""
import time

from google import genai
from google.genai import types

import config

RETRIES = 1                                  # extra tries per model, before moving to the next
RETRY_CODES = {429, 500, 502, 503, 504}      # temporary: busy, rate limited, server hiccup
RETRY_WAIT_SECONDS = 1.5

last_model = None                            # which model answered last (for the counts-only audit log)

SYSTEM_PROMPT = """You are a clinical assistant helping a clinician with pseudonymized clinical documents.
Identifying details have been replaced with pseudonyms like [PATIENT_01], [PROVIDER_01], [HCN_01],
[LOC_01], [ROLE_01], [FAMILY_01]. Dates may have been shifted.
Rules:
- Keep every pseudonym EXACTLY as written, including the brackets. Never invent new ones.
- Never try to guess who or what a pseudonym refers to.
- Keep all medical content: diagnoses, drugs, doses, lab values, intervals and plans.
- Answer only from the documents; say so if they don't contain the answer.

Pseudonymized documents:
---
{note}
---"""

_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set (see .env.example)")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def ask(tagged_note: str, history: list[dict], tagged_question: str) -> str:
    """
    history = [{"role": "user" | "model", "text": "..."}]  (already tagged; the browser keeps it)
    The server keeps nothing between calls, so the full history comes in every time.
    """
    contents = [types.Content(role=h["role"], parts=[types.Part(text=h["text"])]) for h in history]
    contents.append(types.Content(role="user", parts=[types.Part(text=tagged_question)]))

    request_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(note=tagged_note),
        temperature=0.2,
    )
    # Gemini often answers 503 "high demand" (or 429/500) for a while. Retry each model a little,
    # then fall back to the next model in the list, so one busy model doesn't fail the request.
    # Other errors (bad key, blocked request) raise right away. Every model gets the same
    # pseudonymized text; nothing else changes.
    global last_model
    models = [config.GEMINI_MODEL] + [m for m in config.GEMINI_FALLBACK_MODELS if m != config.GEMINI_MODEL]
    for i, model in enumerate(models):
        for attempt in range(RETRIES + 1):
            try:
                response = _get_client().models.generate_content(
                    model=model, contents=contents, config=request_config)
                last_model = model
                return response.text or ""
            except Exception as e:
                busy = getattr(e, "code", None) in RETRY_CODES
                if not busy or (attempt == RETRIES and i == len(models) - 1):
                    raise
                if attempt == RETRIES:
                    break                                      # this model stays busy: try the next
                time.sleep(RETRY_WAIT_SECONDS * (attempt + 1))
    return ""
