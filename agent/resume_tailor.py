"""
Resume / cover-letter tailoring against a job description, using a local
Ollama model. Moderate honesty: the model may reword, reorder, and select
from the master facts and align phrasing to the job description — it may
NOT invent experience, metrics, tools, titles, or dates.

The master fact pool is data/resume_master.json (the only source the model
sees; copy data/resume_master.example.json to start). agent/renderers/
gen_resume.py / gen_cover_letter.py turn the result into .docx.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import uuid
from datetime import date
from pathlib import Path

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
MASTER_PATH = _ROOT / "data" / "resume_master.json"
OUTPUT_DIR = _ROOT / "output"
_GEN_DIR = _HERE / "renderers"

from data import DATA_FILE as DATA_YAML

from .config import GENERATE_TIMEOUT, chat_with_fallback, get_model, make_client
from .profile import file_prefix, load_profile


# ── docx renderers (import the standalone CLI scripts as modules) ──────────────

def _load_gen(name: str):
    spec = importlib.util.spec_from_file_location(name, _GEN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── master / variant loading ──────────────────────────────────────────────────

def _load_master() -> dict:
    if not MASTER_PATH.exists():
        raise FileNotFoundError(
            "data/resume_master.json not found — copy data/resume_master.example.json "
            "and replace it with your own facts")
    return json.loads(MASTER_PATH.read_text(encoding="utf-8"))


def _load_variant(variant_id: str) -> dict:
    import yaml
    try:
        data = yaml.safe_load(DATA_YAML.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    for v in data.get("resume_templates", []):
        if v.get("id") == variant_id:
            return v
    return {}


def _master_corpus(master: dict) -> str:
    """All factual text in the master, lowercased — the fabrication oracle."""
    parts = [master.get("summary", ""), master.get("tagline", "")]
    for job in master.get("experience", []):
        parts += [job.get("company", ""), job.get("role", "")]
        for b in job.get("bullets", []):
            parts += [b.get("lead", ""), b.get("rest", "")]
    fp = master.get("featured_project") or {}
    parts += [fp.get("header", ""), fp.get("role", "")]
    for b in fp.get("bullets", []):
        parts += [b.get("lead", ""), b.get("rest", "")]
    for s in master.get("skills", []):
        parts.append(s.get("content", ""))
    return " ".join(parts).lower()


# ── Ollama ────────────────────────────────────────────────────────────────────

def _chat_json(system: str, user: str, model: str | None = None) -> tuple[dict, str, bool]:
    """Returns (parsed_json, model_used, downgraded)."""
    model = model or get_model(("RESUME_MODEL",))
    client = make_client(timeout=GENERATE_TIMEOUT)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    used, downgraded = model, False
    for attempt in range(2):
        resp, used, downgraded = chat_with_fallback(
            client,
            model=model,
            messages=messages,
            format="json",
            options={"temperature": 0.2},
        )
        model = used
        content = (resp["message"]["content"] if isinstance(resp, dict)
                   else resp.message.content) or ""
        try:
            return json.loads(content), used, downgraded
        except json.JSONDecodeError as exc:
            if attempt == 1:
                raise ValueError(f"model did not return valid JSON: {exc}")
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": (
                f"That was not valid JSON ({exc}). Return ONLY the JSON object, "
                "no prose, no markdown fences."
            )})
    raise ValueError("unreachable")


# ── keyword + fabrication analysis ────────────────────────────────────────────

_STOP = set("""a an the and or of to in for with on at by as is are be from your you
this that these those it its will can has have had we our us role team work
experience years year skills ability strong excellent including etc using use
job description requirements responsibilities preferred plus""".split())


def _keywords(text: str) -> list[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{2,}", text.lower())
    seen, out = set(), []
    for t in toks:
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _resume_text(rj: dict) -> str:
    parts = [rj.get("summary", ""), rj.get("tagline", "")]
    for job in rj.get("experience", []):
        for b in job.get("bullets", []):
            parts += [b.get("lead", ""), b.get("rest", "")]
    fp = rj.get("featured_project") or {}
    for b in fp.get("bullets", []):
        parts += [b.get("lead", ""), b.get("rest", "")]
    for s in rj.get("skills", []):
        parts.append(s.get("content", ""))
    return " ".join(parts).lower()


def _keyword_report(job_description: str, resume_json: dict, corpus: str) -> dict:
    jd_kw = _keywords(job_description)
    rtext = _resume_text(resume_json)
    matched = [k for k in jd_kw if k in rtext]
    missing = [k for k in jd_kw if k not in rtext]

    # Fabrication oracle: every number (with its %, x or + suffix) in the tailored
    # resume must appear as a whole number token in the master corpus. Whole
    # tokens, not substrings: "5" must not pass because the corpus says "2025".
    corpus_nums = {n.rstrip(".,") for n in re.findall(r"\b\d[\d,.]*", corpus)}
    unverified = []
    for tok in re.findall(r"\b\d[\d,.]*\s?(?:%|x|×|\+)?", rtext):
        norm = tok.strip()
        if norm and norm.rstrip("%x×+ ").rstrip(".,") not in corpus_nums:
            unverified.append(norm)
    seen = set()
    unverified = [u for u in unverified if not (u in seen or seen.add(u))]

    coverage = round(100 * len(matched) / max(1, len(jd_kw)))
    return {
        "matched": matched[:40],
        "missing": missing[:40],
        "unverified": unverified,
        "coverage_pct": coverage,
    }


# ── prompts ───────────────────────────────────────────────────────────────────

_HONESTY = (
    "RULES (strict):\n"
    "- You may ONLY use facts present in MASTER. Do not invent or alter "
    "companies, titles, dates, metrics, numbers, tools, or projects.\n"
    "- You MAY reword bullets, reorder them, drop irrelevant ones, and align "
    "phrasing/keywords to the JOB so it reads as a strong match.\n"
    "- Every number, %, and tool you write MUST already appear in MASTER.\n"
    "- Keep it to one page worth of content (most relevant 5-7 experience "
    "bullets). Lead bullets with strong action verbs."
)

_RESUME_SCHEMA = (
    'Return ONLY this JSON object:\n'
    '{"tagline": str, "summary": str, '
    '"experience": [{"company": str, "role": str, "location": str, '
    '"dates": str, "bullets": [{"lead": str, "rest": str}]}], '
    '"featured_project": {"header": str, "role": str, "location": str, '
    '"dates": str, "bullets": [{"lead": str, "rest": str}]}, '
    '"skills": [{"label": str, "content": str}]}\n'
    "company/role/location/dates/header MUST be copied verbatim from MASTER."
)


def tailor_resume(job_description: str, variant_id: str,
                  model: str | None = None) -> dict:
    master = _load_master()
    variant = _load_variant(variant_id)
    corpus = _master_corpus(master)

    emphasis = variant.get("skills_emphasis") or []
    system = (
        f"You are an expert resume strategist tailoring {master['name']}'s resume "
        f"to a specific job. Target angle: {variant.get('name', variant_id)}.\n\n"
        f"{_HONESTY}\n\n{_RESUME_SCHEMA}"
    )
    user = (
        f"MASTER (the only facts you may use):\n{json.dumps(master)}\n\n"
        f"VARIANT EMPHASIS (prioritize these themes if supported by MASTER): "
        f"{', '.join(emphasis)}\n\n"
        f"JOB DESCRIPTION:\n{job_description.strip()}\n\n"
        "Produce the tailored resume JSON now."
    )

    tj, used_model, downgraded = _chat_json(system, user, model)

    # Identity fields are never model-controlled.
    resume_json = {
        "name": master["name"],
        "contact": master["contact"],
        "tagline": tj.get("tagline") or master["tagline"],
        "summary": tj.get("summary") or master["summary"],
        "experience": tj.get("experience") or master["experience"],
        "featured_project": tj.get("featured_project") or master.get("featured_project"),
        "skills": tj.get("skills") or master["skills"],
        "education": master["education"],
        "education_date": master.get("education_date", ""),
    }

    report = _keyword_report(job_description, resume_json, corpus)
    preview = _resume_preview(resume_json)
    token = _stash("resume", resume_json,
                    label=_slug(_first_words(job_description) or variant_id))
    return {"tailored": preview, "keyword_report": report, "doc_token": token,
            "model_used": used_model, "downgraded": downgraded}


_LETTER_SCHEMA = (
    'Return ONLY this JSON object:\n'
    '{"paragraphs": [str, str, str]}\n'
    "3-4 paragraphs: hook, fit/evidence (real metrics from MASTER), close."
)


def generate_cover_letter(company: str, role: str, variant_id: str,
                          model: str | None = None) -> dict:
    master = _load_master()
    variant = _load_variant(variant_id)
    hook = variant.get("cover_letter_hook", "")

    system = (
        f"You write concise, specific cover letters for {master['name']}.\n\n"
        f"{_HONESTY}\n\n{_LETTER_SCHEMA}"
    )
    user = (
        f"MASTER (only facts you may use):\n{json.dumps(master)}\n\n"
        f"ANGLE HOOK: {hook}\n\n"
        f"COMPANY: {company}\nROLE: {role}\n\n"
        "Write the cover letter paragraphs now."
    )
    lj, used_model, downgraded = _chat_json(system, user, model)
    paragraphs = lj.get("paragraphs") or []
    if not isinstance(paragraphs, list) or not paragraphs:
        paragraphs = [hook or "I am writing to express my interest in this role."]

    letter_json = {
        "name": master["name"],
        "contact": master["contact"],
        "date": date.today().strftime("%B %-d, %Y") if os.name != "nt"
                else date.today().strftime("%B %#d, %Y"),
        "recipient": f"Hiring Team, {company}",
        "paragraphs": [str(p) for p in paragraphs],
        "closing": "Best,",
        "signature": load_profile()["name"] or master["name"].title(),
    }
    preview = (
        f"{letter_json['date']}\n{letter_json['recipient']}\n\n"
        + "\n\n".join(letter_json["paragraphs"])
        + f"\n\n{letter_json['closing']}\n{letter_json['signature']}"
    )
    token = _stash("cover", letter_json,
                    label=_slug(f"{company}_{role}"))
    return {"letter": preview, "doc_token": token,
            "model_used": used_model, "downgraded": downgraded}


# ── preview / docx render / token store ───────────────────────────────────────

def _resume_preview(rj: dict) -> str:
    lines = [rj["name"], rj["contact"], rj["tagline"], "",
             "PROFESSIONAL SUMMARY", rj["summary"], "", "PROFESSIONAL EXPERIENCE"]
    for job in rj.get("experience", []):
        lines.append(f"\n{job['company']} | {job['role']}  ({job['dates']})")
        for b in job.get("bullets", []):
            lines.append(f"  • {b.get('lead','')}{b.get('rest','')}")
    fp = rj.get("featured_project")
    if fp:
        lines.append(f"\nFEATURED PROJECT\n{fp['header']} | {fp['role']}  ({fp['dates']})")
        for b in fp.get("bullets", []):
            lines.append(f"  • {b.get('lead','')}{b.get('rest','')}")
    lines.append("\nTECHNICAL SKILLS")
    for s in rj.get("skills", []):
        lines.append(f"  {s.get('label','')} {s.get('content','')}")
    lines.append(f"\nEDUCATION\n{rj['education']}  ({rj.get('education_date','')})")
    return "\n".join(lines)


_STORE: dict[str, tuple[str, dict, str]] = {}  # insertion-ordered; capped
_STORE_MAX = 20


def _stash(kind: str, payload: dict, label: str) -> str:
    tok = uuid.uuid4().hex[:12]
    _STORE[tok] = (kind, payload, label)
    while len(_STORE) > _STORE_MAX:
        _STORE.pop(next(iter(_STORE)))
    return tok


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", (s or "").strip()).strip("-")[:40] or "tailored"


def _first_words(s: str, n: int = 4) -> str:
    return " ".join((s or "").split()[:n])


def render_docx(doc_token: str) -> Path:
    if doc_token not in _STORE:
        raise KeyError("unknown doc_token")
    kind, payload, label = _STORE[doc_token]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if kind == "resume":
        gen = _load_gen("gen_resume")
        out = OUTPUT_DIR / f"{file_prefix()}_{label}_resume.docx"
    else:
        gen = _load_gen("gen_cover_letter")
        out = OUTPUT_DIR / f"{file_prefix()}_{label}_cover.docx"
    doc = gen.build(payload)
    doc.save(str(out))
    return out
