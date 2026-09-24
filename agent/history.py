"""
history.py — Persistent Linda chat history.
Stores conversations in chat_history.jsonl (one JSON object per line).
Capped at MAX_ENTRIES to prevent unbounded growth.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).parent.parent / "chat_history.jsonl"
MAX_ENTRIES = 200


def load_history(limit: int = 20) -> list[dict]:
    """Return the most recent `limit` chat entries, newest last."""
    if not HISTORY_FILE.exists():
        return []
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries[-limit:]
    except Exception:
        log.exception("Failed to load chat history")
        return []


def append_entry(query: str, answer: str, tools_used: list[str]) -> None:
    """Append a new chat entry. Trims file to MAX_ENTRIES if needed."""
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "query": query[:500],   # cap to prevent huge entries
        "answer": answer[:2000],
        "tools_used": tools_used[:20],
    }
    try:
        # Read existing, trim, rewrite if over limit
        existing = []
        if HISTORY_FILE.exists():
            for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        existing.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        existing.append(entry)

        # Trim to MAX_ENTRIES
        if len(existing) > MAX_ENTRIES:
            existing = existing[-MAX_ENTRIES:]
            HISTORY_FILE.write_text(
                "\n".join(json.dumps(e) for e in existing) + "\n",
                encoding="utf-8"
            )
        else:
            # Append-only (fast path)
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    except Exception:
        log.exception("Failed to append chat history entry")


def clear_history() -> None:
    """Delete all history."""
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
