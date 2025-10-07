from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, List, Dict, Any, Mapping

Record = Mapping[str, Any]


@dataclass
class Action:
    tool: str
    name: str
    args: Dict[str, Any]


@dataclass
class PlanStep:
    record_id: str
    actions: List[Action]
    planned_at_ms: int


# ----- Agent protocol -----

class Agent(Protocol):
    def plan(self, record: Record, intent: Any) -> List[Action]:
        """Return proposed actions for a single record. No side effects."""


# ----- Baseline rule-based agent -----

class SimpleRuleAgent:
    """
    A tiny, deterministic agent for bootstrapping.
    - Looks for keywords and chooses a queue.
    - Adds a private note when uncertain.
    """

    def __init__(self) -> None:
        self.rules = [
            ("payment", "billing"),
            ("charge", "billing"),
            ("invoice", "billing"),
            ("refund", "billing"),
            ("crash", "bug"),
            ("error", "bug"),
            ("fail", "bug"),
            ("how", "howto"),
            ("where", "howto"),
            ("can I", "howto"),
        ]

    def plan(self, record: Record, intent: Any) -> List[Action]:
        text = (record.get("text") or "").lower()
        queue = None
        for kw, q in self.rules:
            if kw in text:
                queue = q
                break
        actions: List[Action] = []
        # Respect intent.tooling surface (names only for now)
        allowed_tools = [t.name for t in intent.tooling.allowed_tools] if getattr(intent, "tooling", None) else []
        tool_name = allowed_tools[0] if allowed_tools else "issue_tracker"

        if queue:
            actions.append(Action(tool=tool_name, name="ticket.route", args={"queue": queue}))
            actions.append(Action(tool=tool_name, name="ticket.tag", args={"tag": f"pred:{queue}"}))
        else:
            actions.append(Action(tool=tool_name, name="ticket.route", args={"queue": "general"}))
            actions.append(Action(tool=tool_name, name="ticket.note_private", args={"text": "Uncertain—needs review"}))

        return actions


def now_ms() -> int:
    return int(time.time() * 1000)
