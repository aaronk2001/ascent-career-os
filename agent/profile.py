"""Personal profile for Linda and the resume / interview / offer helpers.

Lives in profile.yaml at the app root (override with ASCENT_PROFILE). The file is
personal and never committed; every key has a neutral default so a fresh install
runs without one. See profile.example.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

import yamlio

PROFILE_FILE = Path(os.environ.get("ASCENT_PROFILE") or Path(__file__).parent.parent / "profile.yaml")

_DEFAULTS = {
    "name": "",                    # full name: prompts, cover-letter signature, .docx file names
    "market": "",                  # default job-market location, e.g. "Denver, CO"
    "about": "",                   # markdown block injected into Linda's system prompt
    "current_salary": None,        # offer math baseline
    "target_salary": None,         # offer verdict threshold
    "monthly_expenses": None,      # offer take-home / gap-cost math
    "net_worth": None,
    "target_net_worth_1yr": None,
    "achievements": [],            # interview-prep bullets
    "star_situation": "",          # default STAR "Situation" line
    "star_result": "",             # default STAR "Result" line
    "talking_points": [],          # company-intel talking points; "{company}" is substituted
    "after_tax_rate": 0.74,        # rough take-home share of gross pay for offer comparisons
}


def load_profile() -> dict:
    try:
        data = yamlio.load(PROFILE_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    return {**_DEFAULTS, **{k: v for k, v in data.items() if k in _DEFAULTS and v is not None}}


def first_name(p: dict | None = None) -> str:
    name = (p or load_profile())["name"].strip()
    return name.split()[0] if name else ""


def file_prefix(p: dict | None = None) -> str:
    return "".join((p or load_profile())["name"].split()) or "Candidate"
