from __future__ import annotations

from dataclasses import dataclass
from typing import Set

from .agent_iface import Action
from .contract import Intent


@dataclass
class PolicyDecision:
    allow: bool
    gate: bool
    reason: str | None = None


def _suffix(name: str) -> str:
    # Normalize comparisons to the action name (e.g., "ticket.route")
    return name.split(".", 1)[-1] if "." in name else name


def _allowed_tool_actions(intent: Intent) -> Set[str]:
    # Build a set like {"issue_tracker:ticket.route", "issue_tracker:ticket.tag", ...}
    allowed: Set[str] = set()
    if getattr(intent, "tooling", None):
        for t in intent.tooling.allowed_tools:
            for a in t.actions:
                allowed.add(f"{t.name}:{a}")
    return allowed


def check(intent: Intent, action: Action) -> PolicyDecision:
    """
    Local policy (MVP):
    - Disallow actions whose suffix is listed in intent.forbidden_actions (e.g., "ticket.close").
    - Require gate for actions whose suffix is in intent.human_only_gates.
    - Disallow actions not present in intent.tooling.allowed_tools / actions.
    """
    full = f"{action.tool}:{action.name}"
    suffix = _suffix(action.name)
    allowed_surface = _allowed_tool_actions(intent)

    # Tool/action surface check
    if allowed_surface and full not in allowed_surface:
        return PolicyDecision(allow=False, gate=False, reason=f"Not in allowed tools/actions: {full}")

    # Forbidden hard block
    if suffix in set(intent.forbidden_actions or []):
        return PolicyDecision(allow=False, gate=False, reason=f"Forbidden action: {suffix}")

    # Human-only gate
    if suffix in set(intent.human_only_gates or []):
        return PolicyDecision(allow=True, gate=True, reason=f"Human approval required: {suffix}")

    return PolicyDecision(allow=True, gate=False, reason=None)
