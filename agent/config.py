"""
Shared LLM/app settings — single source of truth for Linda and the resume
generator. Persisted to career-planner/settings.yaml.

Precedence for model/host: explicit env override > settings.yaml > default.
`chat_with_fallback` auto-downgrades to a model that fits when the chosen one
fails Ollama's memory check.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

import yamlio

SETTINGS_FILE = Path(os.environ.get("ASCENT_SETTINGS") or Path(__file__).parent.parent / "settings.yaml")

DEFAULT_HOST = "http://localhost:11434"
# Small enough to load on a laptop with limited free RAM.
FALLBACK_MODEL = "qwen2.5:1.5b-instruct"
DEFAULT_MODEL = FALLBACK_MODEL

# Hard timeouts (seconds) so a wedged Ollama can never hang a request forever.
PROBE_TIMEOUT = 3      # list()/reachability checks
CHAT_TIMEOUT = 120     # agent-loop chat turns
GENERATE_TIMEOUT = 300 # resume/cover-letter JSON generations


def make_client(timeout: float = CHAT_TIMEOUT):
    """Ollama client pinned to the configured host with a hard timeout."""
    import ollama
    return ollama.Client(host=get_host(), timeout=timeout)

# Curated picks shown in the Settings model picker / pull control.
CURATED_MODELS = [
    {"name": "qwen2.5:1.5b-instruct", "tier": "reliable",
     "note": "~1 GB · always loads here · default"},
    {"name": "qwen3:4b", "tier": "better",
     "note": "~2.5 GB · needs ~4 GiB free RAM"},
    {"name": "qwen2.5:7b-instruct", "tier": "best",
     "note": "~4.7 GB · close apps to free RAM first"},
]

_DEFAULTS = {"ollama_host": DEFAULT_HOST, "model": DEFAULT_MODEL,
             "target_date": None,               # plan target shown in briefs
             "weekly_target": 20,               # apps/week goal
             "bucket_targets": {"az": 12, "remote": 8},
             # job-sprint anchors (set in Settings): sprint day 1, signed-offer
             # target, stretch first offer, runway end, bridge-income decision gate
             "sprint_start": None,
             "offer_date": None,
             "stretch_date": None,
             "runway_end": None,
             "bridge_gate": None,
             "daily_apps": 4,
             "bridge_mode": False,              # bridge_weekday template on weekdays
             # health: target weight, starting weight, direction
             "weight_goal": None,
             "weight_start": None,
             "weight_mode": "cut",              # cut | bulk | maintain
             # Mifflin-St Jeor inputs; daily_delta is applied per weight_mode
             # (cut subtracts, bulk adds, maintain ignores it)
             "height_in": None,
             "birth_year": None,
             "sex": None,                       # male | female
             "daily_delta": 500,
             "goal_date": None,    # target date; drives the required delta
             "cert_budget": None}  # cap on active-cert cost_usd; None = no cap shown

# Keys persisted as trimmed strings; others (ints, dicts) pass through verbatim.
# keys the UI is allowed to blank back out
_NULLABLE_KEYS = {"weight_goal", "weight_start", "height_in", "birth_year", "sex", "goal_date",
                  "cert_budget"}
_STRING_KEYS = {"ollama_host", "model", "target_date", "sprint_start", "offer_date", "stretch_date",
                "runway_end", "bridge_gate", "weight_mode", "sex", "goal_date"}


# mtime-keyed parse cache: load_settings() is called several times per request
# (plan, dayplan, anchors, reminders) and re-parsed settings.yaml every time.
# save_settings() rewrites the file, so mtime invalidation is automatic.
_CACHE: tuple[float, dict] | None = None


def load_settings() -> dict:
    global _CACHE
    try:
        mtime = SETTINGS_FILE.stat().st_mtime
    except OSError:
        mtime = None
    if mtime is None:
        data = {}
    elif _CACHE and _CACHE[0] == mtime:
        data = _CACHE[1]
    else:
        try:
            data = yamlio.load(SETTINGS_FILE.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        _CACHE = (mtime, data)
    return {**_DEFAULTS, **{k: v for k, v in data.items() if k in _DEFAULTS}}


def save_settings(patch: dict) -> dict:
    cur = load_settings()
    for k in _DEFAULTS:
        if k not in patch:
            continue
        # None normally means "not supplied" so a partial patch can't wipe a key;
        # the nullable ones are genuinely clearable from the UI.
        if patch[k] in (None, "") and k in _NULLABLE_KEYS:
            cur[k] = None
        elif patch[k] not in (None, "") or isinstance(patch[k], bool):
            cur[k] = str(patch[k]).strip() if k in _STRING_KEYS else patch[k]
    SETTINGS_FILE.write_text(
        yaml.dump(cur, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return cur


def get_host() -> str:
    return os.environ.get("OLLAMA_HOST") or load_settings()["ollama_host"]


def get_model(env_keys: tuple[str, ...] = ("LINDA_MODEL", "RESUME_MODEL")) -> str:
    # The Settings UI is authoritative: an explicitly saved model wins over a
    # (possibly stale) .env override. Env is only the bootstrap default when
    # no settings.yaml exists yet.
    if SETTINGS_FILE.exists():
        m = load_settings().get("model")
        if m:
            return m
    for k in env_keys:
        if os.environ.get(k):
            return os.environ[k]
    return load_settings()["model"]


def _is_memory_error(exc: Exception) -> bool:
    return "more system memory" in str(exc).lower()


def chat_with_fallback(client, *, model: str, **kwargs):
    """client.chat with one automatic downgrade to FALLBACK_MODEL on an
    Ollama out-of-memory refusal. Returns (response, used_model, downgraded)."""
    try:
        return client.chat(model=model, **kwargs), model, False
    except Exception as exc:
        if _is_memory_error(exc) and model != FALLBACK_MODEL:
            return (client.chat(model=FALLBACK_MODEL, **kwargs),
                    FALLBACK_MODEL, True)
        raise


# ── Claude (Anthropic) backend — optional fallback ──────────────────────────────
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def get_claude_model() -> str:
    return (os.environ.get("LINDA_CLAUDE_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or DEFAULT_CLAUDE_MODEL)


def get_anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY")
