"""Point every data path at a throwaway folder before any app module is imported,
so the suite can never read or write a real career.db / settings.yaml / profile.yaml."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="ascent-tests-"))
for _key, _name in (("ASCENT_DB", "career.db"), ("ASCENT_SETTINGS", "settings.yaml"),
                    ("ASCENT_PROFILE", "profile.yaml"), ("TRACKER_DATA", "data.yaml"),
                    ("ASCENT_SCHEDULE", "schedule.yaml"), ("ASCENT_JOB_RUNS", "job_runs"),
                    ("ASCENT_PROJECTS_ROOT", "projects")):
    os.environ[_key] = str(_TMP / _name)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
