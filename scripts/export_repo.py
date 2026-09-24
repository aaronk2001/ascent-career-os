"""Export the publishable Ascent repo into a separate folder.

    python scripts/export_repo.py C:/path/to/ascent-career-os

Wipes everything in the target except .git/, copies an explicit allowlist of
source paths plus the publish/ overlay (README, CI, setup scripts, screenshots),
then scans the result for personal strings and secret patterns and exits non-zero
on any hit. Anything not on the allowlist — career.db, settings.yaml, profile.yaml,
data.yaml, notes, backups, docs/career, output/ — never leaves this folder.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "publish"

FILES = [
    "app.py", "anchors.py", "certs.py", "data.py", "dayplan.py", "db.py", "focus.py", "gcal.py",
    "glossary.py", "health.py", "jobruns.py", "news.py", "notifier.py", "plan.py", "projects.py",
    "registry.py", "reminders.py", "roadmaps.py", "timeline_board.py", "tracker.py", "yamlio.py",
    "schedule.yaml", "vocab_definitions.yaml", "engineering_formulas.yaml",
    "controls_track.yaml", "ml_track.yaml", "profile.example.yaml",
    "requirements.txt", "requirements-optional.txt", "requirements-dev.txt",
    "ascent.bat", "ascent.vbs", "ascent-dev.bat", "ascent.ico", "create_shortcut.ps1",
    "data/resume_master.example.json",
    "docs/gcal-setup.md",
    "frontend/index.html", "frontend/package.json", "frontend/bun.lock",
    "frontend/tsconfig.json", "frontend/vite.config.ts",
    "scripts/seed_demo.py", "scripts/export_repo.py", "scripts/bench_launch.py",
    "scripts/seed_cert_research.py", "scripts/cert_research_seed.json",
    "scripts/migrate_ml_track_v2.py",
    "scripts/register_tasks.ps1", "scripts/unregister_tasks.ps1",
]
GLOBS = [  # (dir, pattern) — recursive where the pattern says so
    ("agent", "*.py"), ("agent/renderers", "*.py"),
    ("tracks", "*.yaml"), ("data/job_profiles", "*.json"), ("data/roadmaps", "*.json"),
    ("tests", "*.py"), ("frontend/src", "**/*.ts"), ("frontend/src", "**/*.css"),
]
EXCLUDE = {"agent/models.py"}  # unused personal-finance calculator

# Personal identifiers that must never appear in the export, one per line, checked
# case-insensitively. Kept in a local file that is itself never exported.
DENY_FILE = Path(__file__).with_name(".export_denylist.txt")
DENY = [ln.strip().lower() for ln in (DENY_FILE.read_text(encoding="utf-8").splitlines()
                                      if DENY_FILE.exists() else []) if ln.strip() and not ln.startswith("#")]
SECRETS = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|\bsk-[A-Za-z0-9]{20,}|tvly-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}"
                     r"|AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY")
BANNED_SUFFIXES = (".db", ".db-wal", ".db-shm", ".docx", ".jsonl", ".env")


def sources():
    out = [ROOT / f for f in FILES]
    for d, pat in GLOBS:
        out += [p for p in (ROOT / d).glob(pat) if ".omc" not in p.parts and "__pycache__" not in p.parts]
    return sorted({p for p in out if p.relative_to(ROOT).as_posix() not in EXCLUDE})


def wipe(target: Path):
    for child in target.iterdir():
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def scan(target: Path) -> list[str]:
    hits = []
    for p in target.rglob("*"):
        if ".git" in p.relative_to(target).parts or not p.is_file():
            continue
        rel = p.relative_to(target).as_posix()
        if p.name.endswith(BANNED_SUFFIXES) or ".bak" in p.name:
            hits.append(f"{rel}: banned file type")
            continue
        if p.suffix in (".png", ".ico", ".lock") or p.name == "bun.lock":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        hits += [f"{rel}: personal string {d!r}" for d in DENY if d in low]
        hits += [f"{rel}: secret-like {m.group(0)[:12]}..." for m in SECRETS.finditer(text)]
    return hits


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    target = Path(sys.argv[1]).resolve()
    if target == ROOT or ROOT in target.parents:
        sys.exit("target must be outside the app folder")
    target.mkdir(parents=True, exist_ok=True)
    wipe(target)
    files = sources()
    missing = [p for p in files if not p.exists()]
    if missing:
        sys.exit(f"allowlisted paths missing: {missing}")
    for src in files:
        copy(src, target / src.relative_to(ROOT))
    overlay = [p for p in OVERLAY.rglob("*") if p.is_file()] if OVERLAY.is_dir() else []
    for src in overlay:
        copy(src, target / src.relative_to(OVERLAY))
    hits = scan(target)
    print(f"exported {len(files)} source files + {len(overlay)} overlay files -> {target}")
    if hits:
        print("PRIVACY SCAN FAILED:\n  " + "\n  ".join(hits))
        sys.exit(1)
    print(f"privacy scan: clean ({len(DENY)} denylist terms, secret patterns, banned file types)")


if __name__ == "__main__":
    main()
