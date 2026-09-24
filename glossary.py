"""
Unified engineering glossary: merges vocab_definitions.yaml (flat term: def,
controls/ML track vocab) with engineering_formulas.yaml (structured EE/ME/
mechanisms entries with formulas). Domains for the flat terms are inferred from
which track's vocab list contains them.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

import yamlio

BASE = Path(__file__).parent


def _load(name: str) -> dict:
    p = BASE / name
    if not p.exists():
        return {}
    try:
        return yamlio.load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


@lru_cache(maxsize=1)
def _track_domains() -> dict:
    dom: dict[str, str] = {}
    for fname, d in (("controls_track.yaml", "controls"), ("ml_track.yaml", "ml")):
        for w in _load(fname).get("weeks", []):
            for v in (w.get("vocab") or []):
                dom.setdefault(str(v).strip(), d)
    return dom


@lru_cache(maxsize=1)
def build() -> dict:
    out: dict[str, dict] = {}
    domains = _track_domains()
    for term, deftext in _load("vocab_definitions.yaml").items():
        out[term] = {"def": str(deftext), "domain": domains.get(term, "general")}
    for term, e in _load("engineering_formulas.yaml").items():
        if isinstance(e, dict):
            out[term] = {"def": e.get("def", ""), "domain": e.get("domain", "general"), "formula": e.get("formula")}
        else:
            out[term] = {"def": str(e), "domain": "general"}
    return out


@lru_cache(maxsize=1)
def as_list() -> list[dict]:
    return [{"term": t, **v} for t, v in build().items()]
