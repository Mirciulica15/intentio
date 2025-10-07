from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .agent_iface import Action
from .contract import Intent


@dataclass
class PolicyDecision:
    allow: bool
    gate: bool = False
    reason: str = ""


def _allowed_index(intent: Intent) -> Dict[tuple, bool]:
    idx: Dict[tuple, bool] = {}
    for t in intent.tooling.allowed_tools or []:
        for a in t.actions or []:
            idx[(t.name, a.name)] = True
    return idx


def _suffix(name: str) -> str:
    # Normalize comparisons to the action name (e.g., "ticket.route")
    return name.split(".")[-1] if name else name


def _matches_suffix(name: str, patterns: list[str]) -> bool:
    suf = _suffix(name)
    for p in patterns or []:
        # match exact suffix OR full name
        if suf == p or name == p or name.endswith("." + p):
            return True
    return False


def check(intent: Intent, action: Action) -> PolicyDecision:
    # 1) must be allowed by tool surface
    allowed = _allowed_index(intent)
    if (action.tool, action.name) not in allowed:
        return PolicyDecision(allow=False, reason=f"not allowed: {action.tool}.{action.name}")

    # 2) forbidden actions by suffix (domain-agnostic)
    if _matches_suffix(action.name, intent.forbidden_actions):
        return PolicyDecision(allow=False, reason=f"forbidden by intent: {action.name}")

    # 3) human-only gate by suffix (domain-agnostic)
    if _matches_suffix(action.name, intent.human_only_gates):
        return PolicyDecision(allow=True, gate=True, reason=f"human gate required: {action.name}")

    # 4) allowed
    return PolicyDecision(allow=True)
