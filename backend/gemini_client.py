"""
The ONLY code that sends anything to Gemini. It only ever receives pseudonymized text.
"""
from google import genai
from google.genai import types

import config

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

    response = _get_client().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT.format(note=tagged_note),
            temperature=0.2,
        ),
    )
    return response.text or ""
