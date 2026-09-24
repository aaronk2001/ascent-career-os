"""
Shared agent-loop primitives — used by both backends.

  - Scratchpad     : in-loop tool-call de-duplicator
  - _execute_tool  : run one tool, return (result, events)
  - helpers        : tool-call normalization + arg coercion
"""
from __future__ import annotations

import json
import logging

from .tools import get_tool

log = logging.getLogger(__name__)

MAX_ITERATIONS = 10
MAX_CALLS_PER_TOOL = 3


class Scratchpad:
    """Tracks tool calls within a single query to detect loops.

    A given tool may be called at most `max_per_tool` times, and never twice
    with identical inputs. Both rules trigger a tool_skip event so the model
    sees a clear signal instead of silently hitting the iteration cap.
    """

    def __init__(self, max_per_tool: int = MAX_CALLS_PER_TOOL):
        self.calls: list[dict] = []
        self.counts: dict[str, int] = {}
        self.max_per_tool = max_per_tool

    def can_call(self, tool_name: str, inp: dict) -> dict:
        count = self.counts.get(tool_name, 0)
        if count >= self.max_per_tool:
            return {
                "allowed": False,
                "warning": (
                    f"'{tool_name}' has already been called {count} times. "
                    f"Use existing results or a different tool."
                ),
            }
        inp_str = json.dumps(inp, sort_keys=True, default=str)
        for prev in self.calls:
            if prev["tool"] != tool_name:
                continue
            if json.dumps(prev["input"], sort_keys=True, default=str) == inp_str:
                return {
                    "allowed": False,
                    "warning": (
                        f"'{tool_name}' was already called with identical inputs. "
                        f"Use the previous result instead."
                    ),
                }
        return {"allowed": True}

    def record(self, tool_name: str, inp: dict, result: dict) -> None:
        self.calls.append({"tool": tool_name, "input": inp, "result": result})
        self.counts[tool_name] = self.counts.get(tool_name, 0) + 1

    def summary(self) -> str:
        return ", ".join(f"{k}×{v}" for k, v in self.counts.items()) or "no tools"


def execute_tool(name: str, inp: dict, scratchpad: Scratchpad):
    """Run a tool, record it, return (result_dict, events_to_yield)."""
    events: list[dict] = [{"type": "tool_start", "tool": name, "input": inp}]

    check = scratchpad.can_call(name, inp)
    if not check["allowed"]:
        log.warning("Scratchpad block: %s — %s", name, check["warning"])
        events.append({"type": "tool_skip", "tool": name, "reason": check["warning"]})
        return {"skipped": True, "reason": check["warning"]}, events

    tool_def = get_tool(name)
    if tool_def is None:
        msg = f"Unknown tool: {name!r}"
        log.error(msg)
        events.append({"type": "tool_error", "tool": name, "error": msg})
        return {"success": False, "error": msg}, events

    try:
        result = tool_def["execute"](inp)
        scratchpad.record(name, inp, result)
        log.debug("Tool %r OK | success=%s", name, result.get("success"))
        events.append({"type": "tool_end", "tool": name})
        return result, events
    except Exception as exc:
        log.error("Tool %r raised: %s", name, exc)
        result = {"success": False, "error": str(exc)}
        events.append({"type": "tool_error", "tool": name, "error": str(exc)})
        return result, events


def normalize_tool_call(tc) -> dict:
    """Coerce an Ollama tool_call (dict OR Pydantic-y object) to a plain dict.

    Returns: {"function": {"name": str, "arguments": dict | str}}
    """
    if isinstance(tc, dict):
        fn = tc.get("function", {}) or {}
        name = fn.get("name", "")
        args = fn.get("arguments", {})
    else:
        fn = tc.function
        name = fn.name
        args = fn.arguments
    return {"function": {"name": name, "arguments": args}}


def coerce_args(raw_args) -> dict:
    """Ollama may return tool arguments as dict or stringified JSON. Tolerate both."""
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return {"_raw": raw_args}
    if raw_args is None:
        return {}
    return dict(raw_args)


def flatten_message(msg):
    """Return (content, tool_calls) from an Ollama response.message dict-or-object."""
    if isinstance(msg, dict):
        return (msg.get("content") or ""), (msg.get("tool_calls") or [])
    content = getattr(msg, "content", None) or ""
    tool_calls = getattr(msg, "tool_calls", None) or []
    return content, tool_calls
