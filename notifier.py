"""Standalone Windows toast notifier for Ascent.

Run by Windows Task Scheduler so reminders fire even when the app is closed.
Degrades to printing if `windows-toasts` is missing, so a misconfigured task
never crashes silently.

    python notifier.py --digest   # morning summary (one toast)  [default]
    python notifier.py --due      # one toast per overdue follow-up / deadline
    python notifier.py --blocks   # hard-stop nudge (goal list has no block times)
                                  # (run every 5 min; dedupes via data/.toast_sent)
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Same .env overrides as the app (ASCENT_DB etc.), loaded before db is imported.
# Optional here: a scheduled task may run under a Python without python-dotenv.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import db  # noqa: E402
import reminders  # noqa: E402

_SENT = Path(__file__).parent / "data" / ".toast_sent"


def _toast(title, body):
    try:
        from windows_toasts import Toast, WindowsToaster
        toaster = WindowsToaster("Ascent")
        t = Toast()
        t.text_fields = [title, body]
        toaster.show_toast(t)
        return True
    except Exception as exc:
        print(f"[notifier] toast unavailable ({exc})\n{title}\n{body}")
        return False


def run_digest():
    reminders.sync_reminders()
    head, _, body = reminders.digest().partition("\n")
    _toast(head or "Ascent", body or "No items today.")


def run_due():
    open_items = reminders.sync_reminders()
    due = [r for r in open_items if r["kind"] in ("followup", "followup_missing", "deadline")]
    if not due:
        _toast("Ascent", "No follow-ups or deadlines due.")
        return
    for r in due[:5]:
        _toast(r["title"], r["body"] or "")


def _already_sent(key):
    today = datetime.now().date().isoformat()
    lines = _SENT.read_text(encoding="utf-8").splitlines() if _SENT.exists() else []
    lines = [l for l in lines if l.startswith(today)]  # drop yesterday's entries
    if f"{today} {key}" in lines:
        return True
    _SENT.parent.mkdir(parents=True, exist_ok=True)
    _SENT.write_text("\n".join(lines + [f"{today} {key}"]) + "\n", encoding="utf-8")
    return False


def run_blocks():
    """Hard-stop nudge only. Today is an ordered goal list, not a timetable —
    a block's `start` is just its sort key, so per-block start toasts would fire
    at times that mean nothing. hard_stop is still a real clock time."""
    import dayplan
    now = datetime.now()
    stop = dayplan.load_schedule().get("hard_stop") or "19:15"
    lo, hi = now.strftime("%H:%M"), (now + timedelta(minutes=5)).strftime("%H:%M")
    if lo <= stop <= hi and not _already_sent("hard_stop"):
        _toast("Hard stop", "Log actuals, tick blocks, generate tomorrow — then off.")


if __name__ == "__main__":
    db.init_db()  # the task may run before the app has ever created the database
    if "--blocks" in sys.argv:
        run_blocks()
    elif "--due" in sys.argv:
        run_due()
    else:
        run_digest()
