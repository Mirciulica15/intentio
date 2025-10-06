from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List

from .agent_iface import Action


@dataclass
class IssueTrackerClient:
    """Mock tool: does nothing but could capture calls later."""

    @staticmethod
    def call(action: Action) -> Dict[str, Any]:
        # No-op execution stub; later we’ll enforce policy and produce side effects.
        return {"ok": True, "action": {"tool": action.tool, "name": action.name, "args": action.args}}


@dataclass
class IssueTrackerClient:
    """Mock tool: records side effects in memory; supports rollback hints."""
    routes: Dict[str, str] = field(default_factory=dict)  # ticket_id -> queue
    tags: Dict[str, List[str]] = field(default_factory=dict)  # ticket_id -> [tags]
    notes: Dict[str, List[str]] = field(default_factory=dict)  # ticket_id -> [notes]

    def call(self, action: Action) -> Dict[str, Any]:
        name = action.name
        args = action.args or {}
        # Expect record_id inside args or within calling context; for simplicity pass as args["id"]
        rec_id = args.get("id", None)

        if name == "ticket.route":
            if rec_id is None:
                return {"ok": False, "error": "missing id"}
            prev = self.routes.get(rec_id)
            self.routes[rec_id] = args["queue"]
            return {"ok": True, "effect": {"type": "route", "id": rec_id, "to": args["queue"], "prev": prev}}

        if name == "ticket.tag":
            if rec_id is None:
                return {"ok": False, "error": "missing id"}
            self.tags.setdefault(rec_id, []).append(args["tag"])
            return {"ok": True, "effect": {"type": "tag", "id": rec_id, "tag": args["tag"]}}

        if name == "ticket.note_private":
            if rec_id is None:
                return {"ok": False, "error": "missing id"}
            self.notes.setdefault(rec_id, []).append(args.get("text", ""))
            return {"ok": True, "effect": {"type": "note", "id": rec_id}}

        return {"ok": False, "error": f"unknown action {name}"}


class Toolset:
    def __init__(self, intent=None):
        self.intent = intent
        self.issue_tracker = IssueTrackerClient()

    def dispatch(self, action: Action) -> Dict[str, Any]:
        from .policy import check as policy_check
        if self.intent is not None:
            decision = policy_check(self.intent, action)
            if not decision.allow:
                return {"ok": False, "blocked": True, "reason": decision.reason}
            if decision.gate:
                return {"ok": False, "gate_required": True, "reason": decision.reason}

        if action.tool == "issue_tracker":
            return self.issue_tracker.call(action)
        return {"ok": False, "error": f"Unknown tool {action.tool}"}
