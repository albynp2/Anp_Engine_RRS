"""Pemanggilan OpenAI yang tipis: satu fungsi, output JSON, log pemakaian token."""
import json
import re
from typing import Any, Tuple

from . import config


def ai_available() -> bool:
    return bool(config.OPENAI_API_KEY)


def _client():
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY belum diisi. Isi di file .env lalu restart container.")
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY, timeout=180)


def extract_json(text: str) -> Any:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except Exception:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b > a:
        return json.loads(text[a:b + 1])
    raise ValueError("Respons AI bukan JSON yang valid")


def _call(system: str, user: str, max_tokens: int) -> Tuple[str, str]:
    c = _client()
    if hasattr(c, "responses"):
        args = dict(model=config.OPENAI_MODEL, instructions=system, input=user,
                    max_output_tokens=max_tokens)
        if config.OPENAI_REASONING_EFFORT:
            args["reasoning"] = {"effort": config.OPENAI_REASONING_EFFORT}
        r = c.responses.create(**args)
        text = r.output_text
        u = getattr(r, "usage", None)
        usage = f"in={getattr(u, 'input_tokens', '?')} out={getattr(u, 'output_tokens', '?')}" if u else ""
    else:  # SDK lama
        r = c.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        text = r.choices[0].message.content
        u = getattr(r, "usage", None)
        usage = f"in={getattr(u, 'prompt_tokens', '?')} out={getattr(u, 'completion_tokens', '?')}" if u else ""
    return text, usage


def complete_json(system: str, user: str, max_tokens: int = 2000) -> Tuple[Any, str]:
    """Panggil model, parse JSON. Coba ulang sekali bila JSON rusak."""
    text, usage = _call(system, user, max_tokens)
    try:
        return extract_json(text), usage
    except Exception:
        text2, usage2 = _call(system + "\nPENTING: balas HANYA satu objek JSON valid.", user, max_tokens)
        return extract_json(text2), f"{usage} + retry {usage2}"
