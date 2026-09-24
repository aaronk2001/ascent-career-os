"""
Reads daily job-pull runs written by an external scheduled job (any script or
agent that follows this layout) into ASCENT_JOB_RUNS (default: data/job_runs/):
  <ASCENT_JOB_RUNS>/YYYY-MM-DD/
Each run has 00_summary.md (ranked table + "why each fits") and per-job folders
NN_<slug>/ with job.md and, optionally, generated *_Resume.docx /
*_CoverLetter.docx files. Pure read-only parsing over the filesystem.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

JOB_RUNS = Path(os.environ.get("ASCENT_JOB_RUNS") or (Path(__file__).parent / "data" / "job_runs"))

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|(.+)$")


def _runs_dir() -> Path:
    return JOB_RUNS


def list_runs() -> list[dict]:
    base = _runs_dir()
    if not base.is_dir():
        return []
    out = []
    for d in base.iterdir():
        if d.is_dir() and _DATE_RE.match(d.name):
            jobs = [f for f in d.iterdir() if f.is_dir() and re.match(r"^\d+_", f.name)]
            out.append({"date": d.name, "job_count": len(jobs)})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def latest_date() -> str | None:
    runs = list_runs()
    return runs[0]["date"] if runs else None


def _parse_table(md: str) -> dict[int, dict]:
    """Rank → {company,title,location,fit,url} from the markdown ranked table."""
    rows: dict[int, dict] = {}
    for line in md.splitlines():
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        try:
            rank = int(cells[0])
        except ValueError:
            continue
        fit = re.sub(r"[^\d.]", "", cells[4]) or None
        rows[rank] = {
            "company": cells[1],
            "title": cells[2],
            "location": cells[3],
            "fit": float(fit) if fit else None,
            "url": cells[5].strip("<> "),
        }
    return rows


def _parse_why_block(body: str) -> dict[int, str]:
    """Local rank → 'why this fits' text from a numbered list."""
    out: dict[int, str] = {}
    for m in re.finditer(r"(?m)^\s*(\d+)\.\s+(.+?)(?=\n\s*\d+\.\s|\Z)", body, re.DOTALL):
        rank = int(m.group(1))
        text = re.sub(r"\s+", " ", m.group(2)).strip()
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # strip bold
        out[rank] = text
    return out


def _parse_why(md: str) -> dict[int, str]:
    """Rank → 'why this fits' paragraph from the '## Why each fits' section."""
    section = md.split("## Why each fits", 1)
    if len(section) < 2:
        return {}
    body = re.split(r"\n##\s", section[1], 1)[0]
    return _parse_why_block(body)


_BUCKET_RE = re.compile(r"(?m)^## BUCKET\s+([A-Z])\b")
_BUCKET_SIZE = 5


def _parse_buckets(md: str) -> tuple[dict[int, dict], dict[int, str]]:
    """Bucketed format (Jun 2026+): three '## BUCKET X' sections, each with a
    ranked 1–5 table and a '**Why these fit:**' list. Global rank = bucket
    offset + local rank, matching the 01–15 folder numbering."""
    table: dict[int, dict] = {}
    why: dict[int, str] = {}
    marks = list(_BUCKET_RE.finditer(md))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(md)
        chunk = md[m.end():end]
        # don't run past the next non-bucket section within the last chunk
        chunk = re.split(r"\n##\s", chunk, 1)[0]
        offset = (ord(m.group(1)) - ord("A")) * _BUCKET_SIZE
        for local, row in _parse_table(chunk).items():
            table[offset + local] = row
        why_part = chunk.split("**Why these fit:**", 1)
        if len(why_part) == 2:
            for local, text in _parse_why_block(why_part[1]).items():
                why[offset + local] = text
    return table, why


def _section(md: str, header: str) -> str:
    parts = md.split(header, 1)
    if len(parts) < 2:
        return ""
    body = re.split(r"\n##\s", parts[1], 1)[0]
    # drop the remainder of the heading line itself (e.g. " (apply order)")
    body = body.split("\n", 1)[1] if "\n" in body else ""
    return body.strip()


def get_run(date: str) -> dict | None:
    if not _DATE_RE.match(date or ""):
        return None
    d = _runs_dir() / date
    if not d.is_dir():
        return None
    summary = d / "00_summary.md"
    md = summary.read_text(encoding="utf-8", errors="replace") if summary.exists() else ""

    if _BUCKET_RE.search(md):
        table, why = _parse_buckets(md)
    else:  # legacy single-table format (pre Jun 2026)
        table, why = _parse_table(md), _parse_why(md)
    intro = re.split(r"\n##\s", md, 1)[0].lstrip("# ").strip() if md else ""

    jobs = []
    for folder in sorted(f for f in d.iterdir() if f.is_dir() and re.match(r"^\d+_", f.name)):
        try:
            rank = int(folder.name.split("_", 1)[0])
        except ValueError:
            rank = len(jobs) + 1
        meta = table.get(rank, {})
        jobs.append({
            "rank": rank,
            "slug": folder.name,
            "company": meta.get("company", folder.name.split("_", 1)[-1]),
            "title": meta.get("title", ""),
            "location": meta.get("location", ""),
            "fit": meta.get("fit"),
            "url": meta.get("url", ""),
            "why": why.get(rank, ""),
            "has_resume": _doc(folder, "resume") is not None,
            "has_cover": _doc(folder, "cover") is not None,
        })
    jobs.sort(key=lambda j: j["rank"])

    return {
        "date": date,
        "intro": intro,
        "patterns": _section(md, "## Notable patterns") or _section(md, "## Patterns and opportunities spotted"),
        "actions": _section(md, "## Action items"),
        "jobs": jobs,
    }


def job_file(date: str, slug: str, which: str) -> Path | None:
    if not _DATE_RE.match(date or "") or "/" in slug or "\\" in slug or ".." in slug:
        return None
    return _doc(_runs_dir() / date / slug, which)


def _doc(folder: Path, which: str) -> Path | None:
    """<Name>_Resume.docx / <Name>_CoverLetter.docx, whatever the name prefix."""
    pattern = "*_Resume.docx" if which == "resume" else "*_CoverLetter.docx"
    return next(iter(sorted(folder.glob(pattern))), None)
