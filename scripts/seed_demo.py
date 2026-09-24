"""Build a fictional demo instance of Ascent: career.db + settings.yaml +
profile.yaml + data.yaml, all in one folder (default: demo/).

    python scripts/seed_demo.py              # -> demo/
    python scripts/seed_demo.py --out /tmp/ascent-demo
    python app.py --demo                     # seeds demo/ if missing, then opens it

Every company, person and number here is made up. Dates are relative to today,
so the demo always looks "mid-sprint"; re-run this script to refresh them.
Re-running wipes and rebuilds the folder's demo files; it refuses to touch the
real career.db next to the app. Optional modules stay at their defaults (off).
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROFILE_YAML = """\
name: Jordan Rivera
market: Denver, CO
about: |
  ## Jordan — quick profile
  - Controls technician, 3 years in packaging automation; moving into a Controls / Robotics Engineer role.
  - Strengths: PLC troubleshooting, vision inspection, fleet reliability.
  - Targets Denver / Front Range or remote-US roles.
current_salary: 68000
target_salary: 92000
monthly_expenses: 2600
achievements:
  - Cut line changeover time 40% by standardizing PLC recipe handling across 12 lines
  - Deployed a vision station that caught 97% of label defects before palletizing
star_situation: On a 12-line packaging floor with a 98% uptime target.
star_result: Changeover time dropped 40% and unplanned downtime fell by a third.
talking_points:
  - Connect your line-reliability work to {company}'s production scale
  - Highlight the PLC and vision tools from the posting you have shipped with
"""

DATA_YAML = """\
resume_templates:
  - id: controls
    name: Controls / Automation
    target_roles: [Controls Engineer, Automation Engineer]
    skills_emphasis: [PLC, Studio 5000, HMI, commissioning]
    cover_letter_hook: I keep production lines running and make them faster to change over.
  - id: robotics
    name: Robotics / Vision
    target_roles: [Robotics Engineer, Vision Engineer]
    skills_emphasis: [ROS 2, machine vision, Python, cobots]
    cover_letter_hook: I ship vision and motion systems that survive the factory floor.
"""

APPS = [  # company, role, status, bucket, location, salary, applied (days ago), fit
    ("Northwind Robotics", "Robotics Engineer I", "onsite", "local", "Boulder, CO", "$85k–$98k", 19, 8.6),
    ("Front Range Automation", "Controls Engineer", "technical", "local", "Denver, CO", "$80k–$95k", 15, 8.9),
    ("Cobalt Motion Systems", "Motion Control Engineer", "phone_screen", "remote", "Remote — US", "$90k–$110k", 11, 7.8),
    ("Mesa Ridge Semiconductor", "Equipment Automation Engineer", "applied", "local", "Colorado Springs, CO", "$88k–$104k", 6, 8.1),
    ("Redline Controls", "PLC Programmer", "offer", "local", "Golden, CO", "$82k", 26, 7.4),
    ("Kestrel Aerospace", "Test Automation Engineer", "applied", "local", "Englewood, CO", "$78k–$92k", 4, 7.2),
    ("Bluefin Packaging", "Automation Technician II", "rejected", "local", "Aurora, CO", "$62k–$70k", 30, 5.9),
    ("Summit Fleet Robotics", "Field Robotics Engineer", "applied", "remote", "Remote — US", "$95k–$115k", 3, 8.3),
    ("Ironwood Integrators", "Controls Engineer I", "discovered", "local", "Lakewood, CO", None, None, 7.9),
    ("Lumen Vision Labs", "Machine Vision Engineer", "discovered", "remote", "Remote — US", "$100k–$120k", None, 7.6),
    ("Canyon Energy Systems", "SCADA Engineer", "phone_screen", "local", "Fort Collins, CO", "$84k–$99k", 9, 7.0),
    ("Atlas Warehouse Automation", "Robotics Integration Engineer", "applied", "remote", "Remote — US", "$92k–$108k", 1, 8.0),
]

PROJECTS = [  # slug, name, category, stack, status, role, one-liner, ship-done keys
    ("line-sorter", "Conveyor sorter cell", "controls", "CODESYS ST + Factory IO", "active",
     "Solo: PLC logic, HMI, test plan",
     "A 3-lane PLC-driven sorter in simulation that routes mixed totes with zero mis-sorts",
     ("repo", "readme", "demo")),
    ("defect-vision", "Edge defect detection", "robotics", "Python + YOLOv8 + Raspberry Pi 5", "active",
     "Solo: dataset, training, deployment",
     "On-device label-defect detection that signals a PLC over Modbus",
     ("repo", "readme", "demo", "bullet", "portfolio")),
    ("fleet-telemetry", "Fleet telemetry dashboard", "infra", "Grafana + Prometheus + MQTT", "active",
     "Built the pipeline and dashboards",
     "One screen that shows which test robots are idle, faulted or charging", ("repo",)),
    ("arm-controller", "6-DOF arm controller", "robotics", "ESP32 + PCA9685 + MicroPython", "shipped",
     "Firmware + web UI", "Browser-controlled 6-servo arm served straight off an ESP32",
     ("repo", "readme", "bullet")),
    ("io-board", "Modbus I/O expansion board", "hardware", "KiCad + STM32", "active",
     "Schematic, layout, bring-up", "8-in/8-out isolated Modbus RTU board for bench rigs", ()),
    ("hmi-kit", "HMI alarm banner kit", "controls", "Ignition Perspective", "paused",
     "Solo", "Reusable alarm banner + shelving pattern for Perspective screens", ()),
]

STORIES = {
    "line-sorter": ("Mixed-SKU totes were hand-sorted at the end of a demo line, capping throughput at ~6 totes/min.",
                    "A CODESYS state machine drives a 3-lane diverter in Factory IO: photo-eye debounce, reject lane, recipe per SKU, alarm latching.",
                    "Simulated throughput 14 totes/min with zero mis-sorts across a 2-hour soak; recipe change takes one HMI tap.",
                    "Built a PLC-driven sorter in simulation that more than doubles throughput and never mis-routes a tote."),
    "defect-vision": ("Label defects were caught by eye at end-of-line, after the pallet was already wrapped.",
                      "YOLOv8n fine-tuned on 1.2k labelled frames, exported to run on a Pi 5; flags defects to a PLC input over Modbus.",
                      "96.8% recall at 31 FPS on-device; benchmark table and demo video are in the README.",
                      "An on-device vision check that catches almost every label defect before it ships."),
    "fleet-telemetry": ("No single place showed which of 40 test robots were idle, faulted or charging.",
                        "MQTT heartbeats into Prometheus, Grafana dashboards per cell, alert rules for stale heartbeats.",
                        "", ""),
}

CERTS = [  # title, provider, phase, status, verdict, reason, cost, exam (days), steps (text, hours, done)
    ("OSHA 10 (General Industry)", "OSHA Outreach", "phase1", "in_progress", "KEEP-NOW",
     "Cheap, fast, and asked for on most plant-floor postings.", 59, 9,
     [("Enroll with an authorized online provider", 0.5, True), ("Modules 1-4: intro, walking surfaces, exits", 2.5, True),
      ("Modules 5-7: electrical, PPE, hazcom", 3, False), ("Final exam + card request", 1, False)]),
    ("Ignition Core Certification", "Inductive University", "phase1", "in_progress", "KEEP-NOW",
     "Free, self-paced, and the SCADA/HMI skill controls postings ask for.", 0, 24,
     [("Create IU account; install Ignition in trial mode", 1, True), ("Gateway + designer basics", 3, True),
      ("Tags, UDTs, alarming", 3, False), ("Perspective views + bindings", 4, False), ("Pass all challenges", 3.5, False)]),
    ("Universal Robots e-Series Core Track", "UR Academy", "phase1", "completed", "DONE",
     "Completed.", 0, None, [("Online modules", 3, True), ("Simulator exercises", 1, True)]),
    ("Rockwell Studio 5000 Logix Designer Level 1", "Rockwell Automation", "phase2", "wishlist", "LATER",
     "The top skill gap, but instructor-led and paid; ask a future employer to fund it.", 1800, None, []),
    ("ISA Certified Automation Professional (CAP)", "ISA", "phase4", "later", "LATER",
     "Engineer-level credential that assumes several years of field experience.", 450, None, []),
    ("NFPA 70E Arc Flash Training", "NFPA", "phase1", "wishlist", "KEEP-NOW",
     "Expected for anyone working on energized panels; 6 h online.", 286, None,
     [("Online course", 6, False), ("Certificate", 0.5, False)]),
]

MILESTONES = [  # text, due (days from today), done
    ("20 tailored applications sent", -6, True),
    ("Portfolio: sorter cell README + demo video", 5, False),
    ("OSHA 10 card in hand", 9, False),
    ("First technical interview passed", 14, False),
    ("Signed offer — Controls / Robotics Engineer (primary goal)", 53, False),
]

SKILLS = [  # skill, priority, proficiency, target, domain, hours, target hours
    ("PLC Programming", "high", 3, 4, "controls", 42, 60),
    ("IEC 61131-3", "high", 2, 4, "controls", 18, 40),
    ("SCADA/HMI", "high", 2, 3, "controls", 9, 30),
    ("Computer Vision", "medium", 3, 3, "ml", 55, 50),
    ("ROS", "medium", 1, 3, "robotics", 6, 40),
    ("PCB Layout", "low", 2, 2, "hardware", 20, 20),
]


def demo_env(out: Path) -> dict:
    """Environment overrides that point the app at a demo folder."""
    return {k: str(v) for k, v in {
        "ASCENT_DB": out / "career.db", "ASCENT_SETTINGS": out / "settings.yaml",
        "ASCENT_PROFILE": out / "profile.yaml", "TRACKER_DATA": out / "data.yaml",
        "ASCENT_SCHEDULE": out / "schedule.yaml", "ASCENT_JOB_RUNS": out / "job_runs",
        "ASCENT_PROJECTS_ROOT": out / "projects",
    }.items()}


def _write_inputs(out: Path, today: date):
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    (out / "settings.yaml").write_text(
        "ollama_host: http://localhost:11434\n"
        "model: qwen2.5:1.5b-instruct\n"
        f"target_date: '{d(53)}'\nweekly_target: 20\n"
        "bucket_targets:\n  local: 12\n  remote: 8\nlocal_label: Denver\n"
        f"sprint_start: '{d(-13)}'\noffer_date: '{d(53)}'\nstretch_date: '{d(38)}'\n"
        f"runway_end: '{d(68)}'\ndaily_apps: 4\ncert_budget: 600\n",
        encoding="utf-8")
    (out / "profile.yaml").write_text(PROFILE_YAML, encoding="utf-8")
    (out / "data.yaml").write_text(DATA_YAML, encoding="utf-8")


def seed(out: Path, today: date):
    import db
    import dayplan
    import registry

    db.init_db()
    iso = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731

    for i, (co, role, status, bucket, loc, sal, ago, fit) in enumerate(APPS):
        applied = iso(-ago) if ago is not None else None
        row = db.create({"company": co, "role": role, "status": status, "bucket": bucket,
                         "location": loc, "salary_range": sal, "applied_date": applied,
                         "fit_score": fit, "source": "company site",
                         "url": f"https://example.com/careers/{co.lower().replace(' ', '-')}"})
        if status in ("phone_screen", "technical", "onsite"):
            db.update(row["id"], {"next_action": "Send thank-you + prep notes", "next_action_due": iso(1 + i % 3)})

    for i, (slug, name, cat, stack, status, role, one_liner, ship) in enumerate(PROJECTS):
        p = db.project_add({"slug": slug, "name": name, "tier": "core", "category": cat, "stack": stack,
                            "status": status, "sort": i, "path": slug, "role": role, "purpose": one_liner,
                            "repo_url": f"https://github.com/jordan-rivera/{slug}" if "repo" in ship else None})
        patch = {"ship": {k: k in ship for k in ("repo", "readme", "demo", "bullet", "portfolio")}}
        if slug in STORIES:
            problem, built, result, pitch = STORIES[slug]
            patch.update(problem=problem, built=built, result=result, pitch=pitch or None)
        db.project_update(p["id"], patch)

    for link in db.links_all():
        if link["key"] == "linkedin":
            db.link_update(link["id"], {"url": "https://www.linkedin.com/in/jordan-rivera-demo", "status": "done",
                                        "checklist": [{**c, "done": True} for c in link["checklist"]]})
        elif link["key"] == "github":
            db.link_update(link["id"], {"url": "https://github.com/jordan-rivera", "status": "in_progress",
                                        "due": iso(4), "checklist": [{**c, "done": n == 0}
                                                                     for n, c in enumerate(link["checklist"])]})
        elif link["key"] == "portfolio":
            db.link_update(link["id"], {"due": iso(12)})

    for i, (title, prov, phase, status, verdict, reason, cost, exam, steps) in enumerate(CERTS):
        c = db.cert_create({"title": title, "provider": prov, "track": phase, "status": status,
                            "cost_usd": cost, "sort": i,
                            "exam_date": iso(exam) if exam is not None else None})
        db.cert_seed_fields(c["id"], {
            "verdict": verdict, "verdict_reason": reason,
            "steps": [{"text": t, "hours": h, "done": done} for t, h, done in steps],
            "how_to": {"url": "https://example.com/certs", "format": "Self-paced online",
                       "booking": "Enroll online; no proctor scheduling needed.",
                       "checked_on": iso(-2)} if steps else None})

    for i, (text, due, done) in enumerate(MILESTONES):
        db.milestone_create({"text": text, "due": iso(due), "sort": i, "done": done})

    for i, (skill, prio, prof, target, dom, hrs, thrs) in enumerate(SKILLS):
        db.skill_create({"skill": skill, "priority": prio, "proficiency": prof, "target_proficiency": target,
                         "domain": dom, "hours_logged": hrs, "target_hours": thrs, "sort": i})

    for tid, objectives, explained, hours in (("controls", 4, 2, 4.5), ("ml", 3, 1, 3.0)):
        wk = registry.load_track(tid)["weeks"][0]
        db.track_set_week(tid, wk["id"], "in_progress")
        db.track_detail_set(tid, wk["id"], objectives_done=(wk.get("deliverables") or [])[:objectives],
                            can_explain_done=(wk.get("can_explain") or [])[:explained], hours=hours)

    for t in (("Resume v3 finalized", -10, "milestone"), ("Informational chat — Front Range Automation", -5, "event"),
              ("Northwind Robotics onsite", 2, "interview")):
        db.timeline_create({"label": t[0], "date": iso(t[1]), "kind": t[2]})

    db.note_create("Ask Front Range about their Studio 5000 version and the on-call rotation.")
    db.note_create("Sorter cell: record the 2-hour soak test for the README video.")

    monday = today - timedelta(days=today.weekday())
    d = monday
    while d <= today:
        blocks = dayplan.generate(d)
        work = [b for b in blocks if b["cat"] != "break"]
        done_n = len(work) if d < today else min(3, len(work))
        for b in work[:done_n]:
            planned = dayplan.minutes_between(b["start"], b["end"])
            db.day_block_update(b["id"], {"status": "done", "actual_min": planned - (5 if len(b["id"]) % 2 else 0)})
        d += timedelta(days=1)


def build(out: Path, today: date | None = None) -> dict:
    """Wipe and rebuild the demo files in `out`; returns the env overrides for it.
    Must run before `db` is imported anywhere in this process."""
    out = Path(out).resolve()
    if out / "career.db" == (ROOT / "career.db").resolve():
        sys.exit("refusing to overwrite the real career.db — pick another --out folder")
    out.mkdir(parents=True, exist_ok=True)
    for name in ("career.db", "career.db-wal", "career.db-shm", "schedule.yaml"):
        (out / name).unlink(missing_ok=True)
    today = today or date.today()
    _write_inputs(out, today)
    env = demo_env(out)
    os.environ.update(env)
    sys.path.insert(0, str(ROOT))
    import db
    assert Path(db.DB_PATH).resolve() == (out / "career.db").resolve(), "db was imported before the demo env was set"
    seed(out, today)
    return env


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "demo"), help="folder for the demo files (default: demo/)")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    build(out)
    print(f"Demo instance written to {out}\n")
    if out == (ROOT / "demo").resolve():
        print(f'Open it:  "{sys.executable}" app.py --demo   (add --browser for no native window)')
    else:
        env = demo_env(out)
        print("Open it from the repo root (PowerShell):")
        print("  " + "; ".join(f'$env:{k}="{v}"' for k, v in env.items()) + f'; & "{sys.executable}" app.py')
        print("Open it from the repo root (bash):")
        print("  " + " ".join(f'{k}="{Path(v).as_posix()}"' for k, v in env.items()) + f' "{sys.executable}" app.py')
    print(json.dumps({"applications": len(APPS), "projects": len(PROJECTS), "certs": len(CERTS)}))


if __name__ == "__main__":
    main()
