"""
Linda — Claude (Anthropic) backend with full tool-loop parity.

Mirrors the event protocol emitted by `_ollama_backend.run` exactly, and reuses
the shared loop primitives (Scratchpad, execute_tool) so tool behaviour is
identical across backends. Used when LINDA_BACKEND=claude, or as the automatic
fallback when Ollama is unreachable (agent.py decides).
"""
from __future__ import annotations

import json
import logging

from ._loop_common import MAX_ITERATIONS, Scratchpad, execute_tool
from .config import get_anthropic_key, get_claude_model
from .prompts import build_system_prompt
from .tools import get_anthropic_schemas

log = logging.getLogger(__name__)
MAX_TOKENS = 2048


def run(query: str, context):
    """Generator implementing the Linda agent loop on Anthropic Claude."""
    try:
        import anthropic
    except ImportError:
        yield {"type": "answer", "text": "**The `anthropic` package isn't installed.**\n```\npip install anthropic\n```"}
        yield {"type": "done"}
        return

    key = get_anthropic_key()
    if not key:
        yield {
            "type": "answer",
            "text": (
                "**No `ANTHROPIC_API_KEY` found.** Set it in the environment or `.env`, "
                "or switch Linda to the local Ollama backend (`LINDA_BACKEND=ollama`)."
            ),
        }
        yield {"type": "done"}
        return

    client = anthropic.Anthropic(api_key=key)
    model = get_claude_model()
    system = build_system_prompt(context=context)
    tools = get_anthropic_schemas()
    messages: list[dict] = [{"role": "user", "content": query}]
    scratchpad = Scratchpad()
    iterations = 0

    log.info("Linda start | backend=claude | model=%s | query=%r", model, query[:80])

    while iterations < MAX_ITERATIONS:
        iterations += 1
        yield {"type": "thinking", "iteration": iterations}

        try:
            resp = client.messages.create(
                model=model, max_tokens=MAX_TOKENS, system=system,
                tools=tools, messages=messages, temperature=0.4,
            )
        except Exception as exc:
            log.error("Claude chat error: %s", exc)
            yield {"type": "answer", "text": f"**Claude error:** {exc}"}
            yield {"type": "done"}
            return

        blocks = resp.content
        messages.append({"role": "assistant", "content": [b.model_dump() for b in blocks]})
        tool_uses = [b for b in blocks if b.type == "tool_use"]
        text = "".join(b.text for b in blocks if b.type == "text")

        if resp.stop_reason != "tool_use" or not tool_uses:
            log.info("Linda done | end_turn | iterations=%d | tools=%s", iterations, scratchpad.summary())
            yield {"type": "answer", "text": text or "(no answer)"}
            yield {"type": "done"}
            return

        results = []
        for tu in tool_uses:
            inp = dict(tu.input) if isinstance(tu.input, dict) else {}
            result, events = execute_tool(tu.name, inp, scratchpad)
            for e in events:
                yield e
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(result, default=str)})
        messages.append({"role": "user", "content": results})

    # ── max iterations: force synthesis ───────────────────────────────────────
    log.info("Max iterations reached (%d) — forcing synthesis", MAX_ITERATIONS)
    yield {"type": "thinking", "iteration": "final"}
    try:
        resp = client.messages.create(
            model=model, max_tokens=MAX_TOKENS, system=system,
            messages=[*messages, {
                "role": "user",
                "content": "You have reached the research step limit. Based on the data gathered, give your best final answer now. Do not request more tools.",
            }],
            temperature=0.3,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
    except Exception as exc:
        text = f"**Synthesis error:** {exc}"
    yield {"type": "answer", "text": text or "Unable to synthesize a final answer from the gathered data."}
    yield {"type": "done"}
