"""
Linda — Ollama backend (the only backend).

Runs the agent loop against a local Ollama server (default: qwen3:4b).
"""
from __future__ import annotations

import json
import logging

from ._loop_common import (
    MAX_ITERATIONS,
    Scratchpad,
    coerce_args,
    execute_tool,
    flatten_message,
    normalize_tool_call,
)
from .config import PROBE_TIMEOUT, chat_with_fallback, get_host, get_model, make_client
from .prompts import build_system_prompt
from .tools import get_ollama_schemas

log = logging.getLogger(__name__)


def run(query: str, context):
    """Generator implementing the Linda agent loop on Ollama."""
    try:
        import ollama  # type: ignore
    except ImportError:
        yield {
            "type": "answer",
            "text": (
                "**The `ollama` Python package isn't installed.**\n"
                "```\npip install ollama tavily-python\n```"
            ),
        }
        yield {"type": "done"}
        return

    host = get_host()
    model = get_model(("LINDA_MODEL",))
    client = make_client()
    downgrade_note = ""

    # Probe — fail fast with a useful message instead of timing out
    try:
        make_client(timeout=PROBE_TIMEOUT).list()
    except Exception as exc:
        yield {
            "type": "answer",
            "text": (
                f"**Cannot reach Ollama at `{host}`** — {exc}\n\n"
                f"Start it with:\n```\nollama serve\nollama pull {model}\n```"
            ),
        }
        yield {"type": "done"}
        return

    tools = get_ollama_schemas()
    messages = [
        {"role": "system", "content": build_system_prompt(context=context)},
        {"role": "user", "content": query},
    ]
    scratchpad = Scratchpad()
    iterations = 0

    log.info("Linda start | backend=ollama | model=%s | query=%r", model, query[:80])

    while iterations < MAX_ITERATIONS:
        iterations += 1
        yield {"type": "thinking", "iteration": iterations}

        try:
            response, used, downgraded = chat_with_fallback(
                client,
                model=model,
                messages=messages,
                tools=tools,
                options={"temperature": 0.4},
            )
            if downgraded and not downgrade_note:
                downgrade_note = (
                    f"\n\n---\n_⚠ `{model}` could not load (low free RAM); "
                    f"answered with `{used}`. Free RAM or pick a lighter model "
                    f"in Settings._"
                )
                model = used
        except Exception as exc:
            log.error("Ollama chat error: %s", exc)
            yield {"type": "answer", "text": f"**Ollama error:** {exc}"}
            yield {"type": "done"}
            return

        if isinstance(response, dict):
            msg = response.get("message") or {}
        else:
            msg = response.message

        msg_content, msg_tool_calls = flatten_message(msg)

        # Persist the assistant turn
        assistant_entry: dict = {"role": "assistant", "content": msg_content}
        if msg_tool_calls:
            assistant_entry["tool_calls"] = [normalize_tool_call(tc) for tc in msg_tool_calls]
        messages.append(assistant_entry)

        # No tool calls → final answer
        if not msg_tool_calls:
            log.info(
                "Linda done | end_turn | iterations=%d | tools=%s",
                iterations, scratchpad.summary(),
            )
            yield {"type": "answer", "text": msg_content + downgrade_note}
            yield {"type": "done"}
            return

        # Dispatch each tool call, append a "tool" message per result
        for tc in msg_tool_calls:
            normalized = normalize_tool_call(tc)
            name = normalized["function"]["name"]
            inp = coerce_args(normalized["function"]["arguments"])

            result, events = execute_tool(name, inp, scratchpad)
            for e in events:
                yield e
            messages.append({
                "role": "tool",
                "name": name,
                "content": json.dumps(result, default=str),
            })

    # ── max iterations: force synthesis ───────────────────────────────────────
    log.info("Max iterations reached (%d) — forcing synthesis", MAX_ITERATIONS)
    yield {"type": "thinking", "iteration": "final"}
    try:
        synth, _, _ = chat_with_fallback(
            client,
            model=model,
            messages=[
                *messages,
                {
                    "role": "user",
                    "content": (
                        "You have reached the research step limit. Based on all "
                        "data gathered so far, give your best final answer to "
                        "the original question. Do not call more tools."
                    ),
                },
            ],
            options={"temperature": 0.3},
        )
        if isinstance(synth, dict):
            synth_msg = synth.get("message") or {}
        else:
            synth_msg = synth.message
        text, _ = flatten_message(synth_msg)
        text = text or "Unable to synthesize a final answer from the gathered data."
    except Exception as exc:
        text = f"**Synthesis error:** {exc}"

    yield {"type": "answer", "text": text + downgrade_note}
    yield {"type": "done"}
