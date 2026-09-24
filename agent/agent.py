"""
Linda agent — public entry point.

Backend is chosen by the `LINDA_BACKEND` env var:
  - "ollama"          → always local Ollama
  - "claude"/"anthropic" → always Anthropic Claude
  - unset / "auto"    → Ollama if reachable, else Claude (when ANTHROPIC_API_KEY
                        is set), else Ollama (which surfaces a helpful message).

The loop primitives (Scratchpad, tool dispatch) live in `agent/_loop_common.py`
and are shared by both backends, so tool behaviour is identical.

Event shapes emitted by `run_agent`:
    {"type": "thinking",   "iteration": int | "final"}
    {"type": "tool_start", "tool": str, "input": dict}
    {"type": "tool_end",   "tool": str}
    {"type": "tool_skip",  "tool": str, "reason": str}
    {"type": "tool_error", "tool": str, "error": str}
    {"type": "answer",     "text": str}
    {"type": "done"}
"""
from __future__ import annotations

import os


def _ollama_reachable() -> bool:
    try:
        from .config import PROBE_TIMEOUT, make_client
        make_client(timeout=PROBE_TIMEOUT).list()
        return True
    except Exception:
        return False


def run_agent(query: str, context=None):
    backend = (os.environ.get("LINDA_BACKEND") or "auto").strip().lower()

    if backend in ("claude", "anthropic"):
        from . import _claude_backend
        yield from _claude_backend.run(query, context)
        return

    if backend == "ollama":
        from . import _ollama_backend
        yield from _ollama_backend.run(query, context)
        return

    # auto: prefer local Ollama, fall back to Claude when Ollama is down.
    if _ollama_reachable() or not os.environ.get("ANTHROPIC_API_KEY"):
        from . import _ollama_backend
        yield from _ollama_backend.run(query, context)
    else:
        from . import _claude_backend
        yield from _claude_backend.run(query, context)
