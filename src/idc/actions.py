from __future__ import annotations

from typing import List, Dict, Any

from .agent_iface import Action
from .contract import Intent, ToolDef, ActionDef, ArgSpec


def _tool_index(intent: Intent) -> Dict[str, ToolDef]:
    return {t.name: t for t in (intent.tooling.allowed_tools or [])}


def _action_index(tool: ToolDef) -> Dict[str, ActionDef]:
    return {a.name: a for a in (tool.actions or [])}


def _canonicalize_arg_name(arg_name: str, arg_specs: Dict[str, ArgSpec]) -> str:
    low = arg_name.lower()
    for canon, spec in arg_specs.items():
        if low == canon.lower() or low in [a.lower() for a in (spec.aliases or [])]:
            return canon
    return arg_name  # unknown → keep as-is


def _apply_enum(value: Any, spec: ArgSpec, normalize_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        v = value.strip()
        v = normalize_map.get(v, v)  # global canonicalization (optional)
        if spec.enum:
            by_low = {e.lower(): e for e in spec.enum}
            v = by_low.get(v.lower(), v)
            if v not in spec.enum:
                # safe fallback to last enum value (define your own convention; many use "general")
                v = spec.enum[-1]
        return v
    return value


def validate_and_normalize_actions(intent: Intent, record_id: str, actions: List[Action]) -> List[Action]:
    tools = _tool_index(intent)
    normalize_map = (intent.domain.synonyms
                     if getattr(intent, "domain", None) and intent.domain and intent.domain.synonyms
                     else {})

    normalized_out: List[Action] = []

    for a in actions:
        tool = tools.get(a.tool)
        if not tool:
            continue
        action_def = _action_index(tool).get(a.name)
        if not action_def:
            continue

        arg_specs = action_def.args or {}
        raw_args = dict(a.args or {})

        # Canonicalize argument names (respect aliases)
        canon_args: Dict[str, Any] = {}
        for k, v in raw_args.items():
            canon = _canonicalize_arg_name(k, arg_specs)
            canon_args[canon] = v

        # If "id" is required by schema, ensure it exists (bind to record)
        if "id" in arg_specs and arg_specs["id"].required:
            canon_args.setdefault("id", record_id)

        # Enforce required + enums
        missing_required = False
        for name, spec in arg_specs.items():
            if spec.required and name not in canon_args:
                missing_required = True
                break
            if name in canon_args:
                canon_args[name] = _apply_enum(canon_args[name], spec, normalize_map)
        if missing_required:
            continue

        normalized_out.append(Action(tool=a.tool, name=a.name, args=canon_args))

    # Minimality: keep the first occurrence per (tool, action)
    seen: Dict[tuple, bool] = {}
    filtered: List[Action] = []
    for a in normalized_out:
        key = (a.tool, a.name)
        if key in seen:
            continue
        seen[key] = True
        filtered.append(a)

    # Safety cap
    return filtered[:10]
