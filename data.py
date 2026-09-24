"""Data layer — load/save YAML and input validation constants."""
import os
from pathlib import Path
import yaml

DATA_FILE = Path(os.environ.get("TRACKER_DATA", Path(__file__).parent / "data.yaml"))

ALLOWED_SECTIONS = {
    "projects", "applications", "skills", "certifications",
    "weekly_tasks", "hardware_builds", "side_income", "learning_tracks",
    "timeline",
}

ALLOWED_META_KEYS = {
    "current_phase", "current_week", "total_weeks",
    "target_salary_p1", "target_salary_p3",
}


def load_data() -> dict:
    with open(DATA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
