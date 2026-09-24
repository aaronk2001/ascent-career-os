"""One-off migration to ML track v2. Dry-run by default; --apply backs up career.db.

- Clears ml week progress in track_week_status, track_progress_detail AND the legacy
  ml_progress table (db._migrate re-backfills from it on every init_db).
- Replaces the 3 v1 ML milestones with 6 phase milestones due at plan.py's projection.
- Adds fleet-anomaly + maintenance-copilot as core projects; CCA-F cert (LATER);
  DeepLearning.AI spec verdict -> CUT.
"""
import gc
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import plan  # noqa: E402

OLD_MS = ("ML computer-vision phase complete (weeks 1–6)", "Ship YOLOv8 + Hailo-8 portfolio demo",
          "ML LLM phase complete (Zero to Hero, weeks 7–18)")
PHASES = (("P1", "Ship the CV anchor", 2), ("P2", "PyTorch for real", 4),
          ("P3", "Time-series + predictive maintenance", 6), ("P4", "MLOps — take it past the prototype", 9),
          ("P5", "GenAI / agentic + CCA-Foundations", 11), ("P6", "Package, publish, apply", 12))
NEW_PROJECTS = (
    ("fleet-anomaly", "fleet-anomaly", "robotics",
     "Predictive maintenance on real sensor data from a 12-node fleet"),
    ("maintenance-copilot", "maintenance-copilot", "agents",
     "Agentic troubleshooting assistant with RAG, MCP tools, evals, and human approval"),
)
CCA_TITLE = "Claude Certified Architect – Foundations"
DL_SPEC_ID = "cert_e9f0cbce"


def run(apply, today):
    log = []
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM track_week_status WHERE track='ml'").fetchone()[0]
        log.append(f"clear {n} ml week-status rows + ml detail rows + legacy ml_progress")
        if apply:
            conn.execute("DELETE FROM track_week_status WHERE track='ml'")
            conn.execute("DELETE FROM track_progress_detail WHERE track='ml'")
            try:
                conn.execute("DELETE FROM ml_progress")
            except sqlite3.OperationalError:
                pass

    for m in db.milestones_all():
        if m["text"] in OLD_MS and not m["done"]:
            log.append(f"delete milestone {m['text']!r}")
            if apply:
                db.milestone_delete(m["id"])

    weeks = plan.schedule(today)["ml"]["weeks"]
    existing = {m["text"] for m in db.milestones_all()}
    for i, (ph, name, last) in enumerate(PHASES):
        text = f"ML {ph} complete — {name}"
        if text in existing:
            continue
        due = weeks[last]["end"]
        log.append(f"add milestone {text!r} due {due}")
        if apply:
            db.milestone_create({"text": text, "due": due, "phase": 2, "sort": i})

    slugs = {p["slug"] for p in db.projects_all()}
    for slug, name, category, purpose in NEW_PROJECTS:
        if slug in slugs:
            continue
        log.append(f"add core project {name}")
        if apply:
            db.project_add({"slug": slug, "name": name, "tier": "core", "status": "planned",
                            "category": category, "purpose": purpose})

    certs = db.certs_all()
    if not any(c["title"] == CCA_TITLE for c in certs):
        log.append(f"add cert {CCA_TITLE!r} (LATER)")
        if apply:
            c = db.cert_create({"title": CCA_TITLE, "provider": "Anthropic", "track": "phase5", "status": "wishlist"})
            db.cert_seed_fields(c["id"], {"verdict": "LATER",
                                          "verdict_reason": "Week 11 of the ML track, after the job sprint",
                                          "how_to": {"url": None, "format": None, "cost_note": None,
                                                     "checked_on": None, "sources": []}})
    dl_spec = next((c for c in certs if c["id"] == DL_SPEC_ID), None)
    if dl_spec and dl_spec.get("verdict") != "CUT":
        log.append(f"{DL_SPEC_ID} verdict -> CUT")
        if apply:
            db.cert_seed_fields(DL_SPEC_ID, {"verdict": "CUT",
                                             "verdict_reason": "Supplement, not a substitute for projects"})
    return log


def dry_run_preview(today):
    """Preview what --apply would do by actually applying it to a throwaway copy
    of the DB — old v1 ml progress in the real DB otherwise skews the projected
    milestone dues (schedule() treats completed/in-progress weeks specially), so
    a preview computed without clearing progress first would be wrong. The real
    db.DB_PATH is never opened for writing here."""
    real_path = db.DB_PATH
    with db.get_conn() as conn:  # flush WAL into the main file so the copy is complete
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    fd, tmp_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    tmp_path = Path(tmp_name)
    shutil.copy2(real_path, tmp_path)
    db.DB_PATH = tmp_path
    try:
        return run(True, today)
    finally:
        db.DB_PATH = real_path
        gc.collect()  # release any lingering sqlite3.Connection to the copy before deleting it
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass  # best-effort cleanup of the throwaway copy; never touches the real DB


def main():
    apply = "--apply" in sys.argv
    today = date.today()
    if apply:
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        shutil.copy2(db.DB_PATH, f"{db.DB_PATH}.bak-ml-v2-{stamp}")
        log = run(True, today)
    else:
        log = dry_run_preview(today)
    for line in log:
        print(line)
    print("APPLIED" if apply else "DRY RUN — re-run with --apply to write")


if __name__ == "__main__":
    main()
