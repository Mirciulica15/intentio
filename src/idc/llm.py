from __future__ import annotations

import json
import os
from typing import Protocol, List, Dict, Any, Optional


class LLMBackend(Protocol):
    def generate_json(self, messages: List[Dict[str, str]], model: str, temperature: float = 0.2) -> Dict[str, Any]: ...


class OpenAIBackend:
    """
    Thin wrapper around OpenAI Chat Completions with JSON response format.
    Keeps vendor specifics isolated behind an interface.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        # Lazy import to avoid hard dependency elsewhere
        from openai import OpenAI
        self._client = OpenAI(api_key=self.api_key)

    def generate_json(self, messages: List[Dict[str, str]], model: str, temperature: float = 0.2) -> Dict[str, Any]:
        # Use JSON mode so the model must return a JSON object
        resp = self._client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except Exception:
            # In case model returns non-JSON, fail closed with empty plan
            return {"actions": []}
