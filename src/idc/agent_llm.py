from __future__ import annotations

from typing import List, Dict, Any

from pydantic import BaseModel, ValidationError

from .agent_iface import Agent, Record, Action
from .contract import Intent
from .llm import LLMBackend


class ActionOut(BaseModel):
    tool: str
    name: str
    args: Dict[str, Any]


class PlanOut(BaseModel):
    actions: List[ActionOut] = []


SYSTEM_TEMPLATE = """You are a planning assistant for enterprise automations.
Plan SAFE, REVERSIBLE actions that align with the intent contract.

Rules:
- Use ONLY the tools/actions and argument schema provided.
- Do NOT emit forbidden or human-only actions.
- Output STRICT JSON: {"actions":[{"tool":str,"name":str,"args":object}, ...]} — no extra text.
- Use canonical arg names (not aliases) as listed in the schema.
- Keep plans minimal and deduplicated.
"""


def _surface_for_prompt(intent: Intent) -> str:
    lines: List[str] = []
    for t in intent.tooling.allowed_tools:
        lines.append(f"- tool: {t.name}")
        for a in t.actions:
            arg_desc = []
            for name, spec in (a.args or {}).items():
                req = "required" if spec.required else "optional"
                enum = f", enum={spec.enum}" if spec.enum else ""
                aliases = f", aliases={spec.aliases}" if spec.aliases else ""
                arg_desc.append(f"{name}({req}{enum}{aliases})")
            lines.append(f"  - action: {a.name} | args: {', '.join(arg_desc) if arg_desc else '(none)'}")
    return "\n".join(lines)


def make_messages(intent: Intent, record: Record) -> list[dict]:
    system = SYSTEM_TEMPLATE + "\n" + \
             f"Purpose: {intent.purpose}\nAllowed surface:\n{_surface_for_prompt(intent)}\n"
    user = {
        "role": "user",
        "content": (
            "Plan actions for this input.\n"
            f"record_id: {record.get('id', '')}\n"
            f"text: {record.get('text', '')}\n"
            "Respond with JSON only."
        )
    }
    return [{"role": "system", "content": system}, user]


class LLMPlanner(Agent):
    def __init__(self, backend: LLMBackend, model: str = "gpt-4o-mini", temperature: float = 0.2):
        self.backend = backend
        self.model = model
        self.temperature = temperature

    def plan(self, record: Record, intent: Intent) -> List[Action]:
        messages = make_messages(intent, record)
        raw = self.backend.generate_json(messages=messages, model=self.model, temperature=self.temperature)
        try:
            parsed = PlanOut.model_validate(raw)
        except ValidationError:
            parsed = PlanOut(actions=[])

        # Map to internal Action; normalization & validation happen downstream
        return [Action(tool=a.tool, name=a.name, args=dict(a.args or {})) for a in parsed.actions]
