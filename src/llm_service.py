import os
from typing import Optional

from dotenv import load_dotenv

try:
    import google.generativeai as genai
except Exception as _e:  # pragma: no cover - optional dep handling
    genai = None


_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _configure() -> None:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found. Please set it in your environment or .env file.")
    if genai is None:
        raise RuntimeError("google-generativeai package is not installed. Add it to requirements.txt and install.")
    genai.configure(api_key=api_key)


def generate_llm_output(prompt: str, model_name: Optional[str] = None) -> str:
    _configure()
    model = genai.GenerativeModel(model_name or _MODEL_NAME)
    response = model.generate_content(prompt)

    # Normalize output text
    text = getattr(response, "text", None)
    if text:
        return text

    # Fallback if the SDK returns candidates
    candidates = getattr(response, "candidates", None)
    if candidates:
        for c in candidates:
            parts = getattr(getattr(c, "content", None), "parts", [])
            for p in parts:
                val = getattr(p, "text", None) or getattr(p, "inline_data", None)
                if isinstance(val, str) and val.strip():
                    return val

    return "(No content returned by the LLM)"


