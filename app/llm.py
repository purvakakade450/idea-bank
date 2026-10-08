"""Minimal Claude (Anthropic Messages API) client using requests."""
import json
import logging
import re

import requests

from .config import Config

log = logging.getLogger(__name__)
API_URL = "https://api.anthropic.com/v1/messages"


class LLMError(Exception):
    pass


def available():
    return bool(Config.ANTHROPIC_API_KEY)


def complete(prompt, system="", max_tokens=2000, temperature=0.4):
    if not available():
        raise LLMError("ANTHROPIC_API_KEY is not set")
    body = {
        "model": Config.ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    try:
        r = requests.post(
            API_URL,
            headers={
                "x-api-key": Config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=120,
        )
    except requests.RequestException as e:
        raise LLMError(f"network error: {e}") from e
    if r.status_code != 200:
        raise LLMError(f"API error {r.status_code}: {r.text[:300]}")
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def parse_json(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0] or [-1])
    if start < 0:
        raise LLMError("no JSON in model reply")
    end = max(t.rfind("}"), t.rfind("]"))
    try:
        return json.loads(t[start:end + 1])
    except ValueError as e:
        raise LLMError(f"bad JSON from model: {e}") from e


def complete_json(prompt, system="", max_tokens=3000):
    sys = (system + "\n" if system else "") + "Reply with valid JSON only. No markdown fences, no commentary."
    return parse_json(complete(prompt, sys, max_tokens=max_tokens, temperature=0.3))
