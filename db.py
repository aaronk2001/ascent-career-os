import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("ASCENT_DB") or Path(__file__).parent / "career.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT DEFAULT 'discovered',
    score REAL,
    url TEXT,
    salary_range TEXT,
    contact_name TEXT,
    contact_email TEXT,
    applied_date TEXT,
    follow_up_date TEXT,
    resume_variant TEXT,
    notes TEXT,
    interview_notes TEXT,
    location TEXT,
    source TEXT,
    bucket TEXT,
    job_run_date TEXT,
    job_run_rank INTEGER,
    job_run_slug TEXT,
    fit_score REAL,
    next_action TEXT,
    next_action_due TEXT,
    last_contacted TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS jobs_status_idx ON applications(status);
CREATE INDEX IF NOT EXISTS jobs_company_role_idx ON applications(company, role);

CREATE TABLE IF NOT EXISTS controls_progress (
    week_id INTEGER PRIMARY KEY,
    status TEXT DEFAULT 'not_started',
    started_at TEXT,
    completed_at TEXT,
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ml_progress (
    week_id INTEGER PRIMARY KEY,
    status TEXT DEFAULT 'not_started',
    started_at TEXT,
    completed_at TEXT,
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── consolidated operational data (migrated out of data.yaml / notes.yaml) ──

CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    phase INTEGER DEFAULT 1,
    text TEXT NOT NULL,
    due TEXT,
    done INTEGER DEFAULT 0,
    sort INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS weekly_actions (
    id TEXT PRIMARY KEY,
    week TEXT NOT NULL,
    text TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    sort INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS weekly_actions_week_idx ON weekly_actions(week);

CREATE TABLE IF NOT EXISTS skill_gaps (
    id TEXT PRIMARY KEY,
    skill TEXT NOT NULL,
    priority TEXT,
    target_hours REAL DEFAULT 0,
    hours_logged REAL DEFAULT 0,
    complete INTEGER DEFAULT 0,
    proficiency INTEGER DEFAULT 0,
    target_proficiency INTEGER DEFAULT 0,
    evidence TEXT DEFAULT '[]',
    domain TEXT,
    related_track TEXT,
    related_profiles TEXT DEFAULT '[]',
    sort INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS certifications (
    id TEXT PRIMARY KEY,
    provider TEXT,
    title TEXT NOT NULL,
    url TEXT,
    track TEXT DEFAULT 'general',
    status TEXT DEFAULT 'wishlist',
    hours REAL,
    cost TEXT,
    notes TEXT,
    category TEXT,
    time_est TEXT,
    why TEXT,
    related_skills TEXT DEFAULT '[]',
    related_profiles TEXT DEFAULT '[]',
    exam_date TEXT,
    cost_usd REAL,
    sort INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    kind TEXT DEFAULT 'milestone',
    label TEXT NOT NULL,
    phase TEXT,
    track TEXT,
    done INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS timeline_date_idx ON timeline_events(date);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    text TEXT NOT NULL,
    edited TEXT,
    pinned INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS notes_ts_idx ON notes(ts DESC);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    due TEXT,
    ref_type TEXT,
    ref_id TEXT,
    read INTEGER DEFAULT 0,
    dismissed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS reminders_open_idx ON reminders(dismissed, read);

CREATE TABLE IF NOT EXISTS track_progress_detail (
    track TEXT NOT NULL,
    week_id INTEGER NOT NULL,
    objectives_done TEXT DEFAULT '[]',
    hours REAL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (track, week_id)
);

-- ── generic per-track week status (replaces controls_progress / ml_progress) ──
CREATE TABLE IF NOT EXISTS track_week_status (
    track TEXT NOT NULL,
    week_id INTEGER NOT NULL,
    status TEXT DEFAULT 'not_started',
    started_at TEXT,
    completed_at TEXT,
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (track, week_id)
);

-- ── live node state over JSON-defined roadmap trees (data/roadmaps/*.json) ──
CREATE TABLE IF NOT EXISTS roadmap_progress (
    roadmap_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    state TEXT DEFAULT 'available',
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (roadmap_id, node_id)
);

-- ── job-sprint (Sep 2026): hour-by-hour day plan, profile links, side revenue ──
CREATE TABLE IF NOT EXISTS day_blocks (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    cat TEXT NOT NULL,
    title TEXT,
    detail TEXT,
    deep_link TEXT,
    source_kind TEXT,
    source_id TEXT,
    status TEXT DEFAULT 'planned',
    actual_min INTEGER DEFAULT 0,
    gcal_event_id TEXT,
    pos INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS day_blocks_date_idx ON day_blocks(date);

CREATE TABLE IF NOT EXISTS profile_links (
    id TEXT PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL,
    url TEXT,
    status TEXT DEFAULT 'todo',
    checklist TEXT DEFAULT '[]',
    due TEXT,
    notes TEXT,
    sort INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ── project inventory + the six interview-story blanks (Sep 2026) ──
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    tier TEXT DEFAULT 'core',
    path TEXT,
    category TEXT,
    stack TEXT,
    status TEXT DEFAULT 'active',
    role TEXT,
    started TEXT,
    ended TEXT,
    repo_url TEXT,
    demo_url TEXT,
    purpose TEXT,
    problem TEXT,
    built TEXT,
    decision TEXT,
    result TEXT,
    differently TEXT,
    pitch TEXT,
    sort INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS projects_tier_idx ON projects(tier, sort);

CREATE TABLE IF NOT EXISTS side_log (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    source TEXT DEFAULT 'clips',
    platform TEXT,
    posts INTEGER DEFAULT 0,
    followers INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    revenue REAL DEFAULT 0,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS side_log_date_idx ON side_log(date);

-- ── personal health: one row per day + an editable workout library ──
CREATE TABLE IF NOT EXISTS health_day (
    id TEXT PRIMARY KEY,
    date TEXT UNIQUE NOT NULL,
    weight_lb REAL,
    split TEXT,
    minutes INTEGER DEFAULT 0,
    routine TEXT DEFAULT '{}',
    note TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS health_day_date_idx ON health_day(date);

CREATE TABLE IF NOT EXISTS workouts (
    id TEXT PRIMARY KEY,
    split TEXT NOT NULL,
    name TEXT NOT NULL,
    sets TEXT,
    note TEXT,
    sort INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

# Seeded once when profile_links is empty: a generic checklist with no due dates
# (set them in Profile Links). Rows are never re-seeded or overwritten.
_PROFILE_LINK_SEED = [
    {"key": "linkedin", "label": "LinkedIn", "url": "", "status": "todo", "due": None, "checklist": [
        {"text": "Headline names the target role and 2-3 core skills", "done": False},
        {"text": "Open-to-work set for target locations + remote", "done": False},
        {"text": "Featured section links your best project demo", "done": False}]},
    {"key": "github", "label": "GitHub", "url": "", "status": "todo", "due": None, "checklist": [
        {"text": "Profile README: who you are, stack, 3 headline projects", "done": False},
        {"text": "Pin the 4-6 repos that best match the target role", "done": False},
        {"text": "Every pinned repo has a one-line description, topics and a README screenshot", "done": False}]},
    {"key": "portfolio", "label": "Portfolio site", "url": "", "status": "todo", "due": None, "checklist": [
        {"text": "Deploy the site (any static host works)", "done": False},
        {"text": "One page per headline project with a demo video or photos", "done": False},
        {"text": "Resume PDF download + contact links", "done": False},
        {"text": "Paste the final URL here and into LinkedIn + GitHub", "done": False}]},
    {"key": "other", "label": "Other (video channel, blog, ...)", "url": "", "status": "todo", "due": None,
     "checklist": [
         {"text": "Pick one channel where demos live", "done": False},
         {"text": "Upload the first project demo", "done": False},
         {"text": "Paste the URL here and link it from LinkedIn + GitHub", "done": False}],
     "notes": "Optional: only worth it once there is a real demo to link."},
]


# Seeded once when `workouts` is empty. Splits match health.GYM_SPLIT; every row
# is editable in the Health section afterwards.
_WORKOUT_SEED = [
    ("push", "Barbell bench press", "4x6-8", "Add 5 lb once you hit 8 reps on all four sets."),
    ("push", "Overhead press", "3x8", "Brace hard, no leg drive."),
    ("push", "Incline DB press", "3x10", "30 degree bench, full stretch at the bottom."),
    ("push", "Dips", "3xAMRAP", "Add weight once you clear 12 bodyweight reps."),
    ("push", "Lateral raise", "3x15", "Light. Elbows lead, no swing."),
    ("push", "Triceps pushdown", "3x12", "Last set to failure."),
    ("pull", "Barbell row", "4x8", "Torso about 45 degrees, pull to the navel."),
    ("pull", "Pull-up", "3xAMRAP", "Band-assist under 5 reps; add weight over 10."),
    ("pull", "Lat pulldown", "3x10", "Only if the pull-ups are already cooked."),
    ("pull", "Face pull", "3x15", "Shoulder health. Do not skip this one, you sit all day."),
    ("pull", "Barbell curl", "3x10", "No swing, 2s negative."),
    ("pull", "Hammer curl", "2x12", "Finisher."),
    ("legs", "Back squat", "4x5", "Add 5 lb a week for as long as depth holds."),
    ("legs", "Romanian deadlift", "3x8", "Hinge, flat back, feel the hamstring stretch."),
    ("legs", "Leg press", "3x12", "Full range, no lockout slam."),
    ("legs", "Walking lunge", "3x10 per leg", "Long stride, knee tracks the toe."),
    ("legs", "Calf raise", "4x15", "One second pause at the top."),
    ("legs", "Hanging leg raise", "3x12", "Core. Control the way down."),
    ("zone2", "Zone-2 cardio", "20 min", "Conversational pace, HR about 130-145. Bike, incline walk or row."),
    ("rest", "Walk", "30 min", "Outside. This counts as the rest-day session."),
    ("rest", "Mobility", "10 min", "Hips and thoracic spine."),
]


def _seed_workouts(conn):
    if conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]:
        return
    for i, (split, name, sets, note) in enumerate(_WORKOUT_SEED):
        conn.execute(
            "INSERT INTO workouts (id, split, name, sets, note, sort) VALUES (?,?,?,?,?,?)",
            [_new_id("wo"), split, name, sets, note, i])


def _seed_profile_links(conn):
    n = conn.execute("SELECT COUNT(*) FROM profile_links").fetchone()[0]
    if n:
        return
    for i, row in enumerate(_PROFILE_LINK_SEED):
        conn.execute(
            "INSERT INTO profile_links (id, key, label, url, status, checklist, due, notes, sort) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [_new_id("lnk"), row["key"], row["label"], row["url"], row["status"],
             json.dumps(row["checklist"]), row["due"], row.get("notes"), i])


def _utcnow():
    """Naive UTC now (same format the rows already store); utcnow() is deprecated."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    # WAL (set persistently in init_db) + NORMAL sync = no full fsync per commit,
    # so the many small writes (reminder upserts, etc.) stop blocking on disk.
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def _migrate(conn):
    # add can_explain_done column to track_progress_detail if missing (dual checklist)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(track_progress_detail)").fetchall()]
    if "can_explain_done" not in cols:
        conn.execute("ALTER TABLE track_progress_detail ADD COLUMN can_explain_done TEXT DEFAULT '[]'")
    # certifications: roadmap fields (category / time estimate / why-it-fits)
    cert_cols = [r[1] for r in conn.execute("PRAGMA table_info(certifications)").fetchall()]
    for col in ("category", "time_est", "why"):
        if col not in cert_cols:
            conn.execute(f"ALTER TABLE certifications ADD COLUMN {col} TEXT")
    # certifications: cross-links (to skills/profiles) + budget/exam-date
    for col, decl in (("related_skills", "TEXT DEFAULT '[]'"), ("related_profiles", "TEXT DEFAULT '[]'"),
                      ("exam_date", "TEXT"), ("cost_usd", "REAL"),
                      ("verdict", "TEXT"), ("verdict_reason", "TEXT"),
                      ("how_to", "TEXT"), ("steps", "TEXT DEFAULT '[]'")):
        if col not in cert_cols:
            conn.execute(f"ALTER TABLE certifications ADD COLUMN {col} {decl}")
    # applications: CRM enrichment (location/source/bucket, daily-pull audit, follow-up automation)
    app_cols = [r[1] for r in conn.execute("PRAGMA table_info(applications)").fetchall()]
    for col, decl in (("location", "TEXT"), ("source", "TEXT"), ("bucket", "TEXT"),
                      ("job_run_date", "TEXT"), ("job_run_rank", "INTEGER"), ("job_run_slug", "TEXT"),
                      ("fit_score", "REAL"), ("next_action", "TEXT"),
                      ("next_action_due", "TEXT"), ("last_contacted", "TEXT")):
        if col not in app_cols:
            conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {decl}")
    # notes: pin support
    note_cols = [r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()]
    if "pinned" not in note_cols:
        conn.execute("ALTER TABLE notes ADD COLUMN pinned INTEGER DEFAULT 0")
    # timeline_events: audit column so silent date changes become traceable
    tl_cols = [r[1] for r in conn.execute("PRAGMA table_info(timeline_events)").fetchall()]
    if "updated_at" not in tl_cols:
        conn.execute("ALTER TABLE timeline_events ADD COLUMN updated_at TEXT")
    # projects: resume/GitHub/portfolio ship checklist (JSON object of 5 bools)
    proj_cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "ship" not in proj_cols:
        conn.execute("ALTER TABLE projects ADD COLUMN ship TEXT")
    # skill_gaps: proficiency model + evidence + roadmap/job linkage (alongside hours)
    sg_cols = [r[1] for r in conn.execute("PRAGMA table_info(skill_gaps)").fetchall()]
    for col, decl in (("proficiency", "INTEGER DEFAULT 0"), ("target_proficiency", "INTEGER DEFAULT 0"),
                      ("evidence", "TEXT DEFAULT '[]'"), ("domain", "TEXT"),
                      ("related_track", "TEXT"), ("related_profiles", "TEXT DEFAULT '[]'")):
        if col not in sg_cols:
            conn.execute(f"ALTER TABLE skill_gaps ADD COLUMN {col} {decl}")
    # backfill generic track_week_status from legacy controls_progress / ml_progress (idempotent)
    for legacy, track in (("controls_progress", "controls"), ("ml_progress", "ml")):
        try:
            rows = conn.execute(f"SELECT * FROM {legacy}").fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            d = dict(r)
            conn.execute(
                "INSERT OR IGNORE INTO track_week_status "
                "(track, week_id, status, started_at, completed_at, notes, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                [track, d["week_id"], d.get("status"), d.get("started_at"),
                 d.get("completed_at"), d.get("notes"), d.get("updated_at")])


def init_db():
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # persistent in the db file header
        conn.executescript(SCHEMA)
        _migrate(conn)
        _seed_profile_links(conn)
        _seed_workouts(conn)

def get_all(status=None, company=None):
    with get_conn() as conn:
        query = "SELECT * FROM applications WHERE status != 'archived'"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
        query += " ORDER BY updated_at DESC"
        return [dict(r) for r in conn.execute(query, params).fetchall()]

def get_one(app_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", [app_id]).fetchone()
        return dict(row) if row else None

APP_COLUMNS = {
    "id", "company", "role", "status", "score", "url", "salary_range",
    "contact_name", "contact_email", "applied_date", "follow_up_date",
    "resume_variant", "notes", "interview_notes", "created_at", "updated_at",
    "location", "source", "bucket", "job_run_date", "job_run_rank",
    "job_run_slug", "fit_score", "next_action", "next_action_due", "last_contacted",
}

# Funnel stage order (archived/rejected handled separately).
STAGE_ORDER = ["discovered", "applied", "phone_screen", "technical", "onsite", "offer"]


def compute_followup_date(applied_date, days=3):
    """Rule-of-Three first follow-up: applied + 3 days (ISO date, or None)."""
    try:
        return (date.fromisoformat(str(applied_date)[:10]) + timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return None

def create(data):
    # whitelist: client JSON keys become SQL column names
    data = {k: v for k, v in dict(data).items() if k in APP_COLUMNS}
    data.setdefault('id', f"app_{uuid.uuid4().hex[:8]}")
    now = _utcnow().isoformat()
    data.setdefault('created_at', now)
    data['updated_at'] = now
    if data.get('status') == 'applied' and not data.get('applied_date'):
        data['applied_date'] = date.today().isoformat()
    # follow-up automation: seed the first nudge 3 days after applying
    if data.get('applied_date') and not data.get('next_action_due'):
        data['next_action_due'] = compute_followup_date(data['applied_date'])
        data.setdefault('next_action', 'Follow up')
    cols = list(data.keys())
    placeholders = ','.join(['?' for _ in cols])
    with get_conn() as conn:
        conn.execute(f"INSERT INTO applications ({','.join(cols)}) VALUES ({placeholders})", [data[c] for c in cols])
    return data

def update(app_id, data):
    data = {k: v for k, v in dict(data).items() if k in APP_COLUMNS - {"id", "created_at"}}
    data['updated_at'] = _utcnow().isoformat()
    sets = ', '.join([f"{k} = ?" for k in data])
    vals = list(data.values()) + [app_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE applications SET {sets} WHERE id = ?", vals)
    return get_one(app_id)

def soft_delete(app_id):
    with get_conn() as conn:
        conn.execute("UPDATE applications SET status = 'archived' WHERE id = ?", [app_id])

def week_start(today=None):
    """Monday of the current week: the window weekly targets count against,
    the same one Today's week budget (/api/day/week) uses."""
    today = today or date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def get_stats():
    today = date.today().isoformat()
    monday = week_start()
    apps = get_all()
    by_stage = {}
    for a in apps:
        s = a['status']
        by_stage[s] = by_stage.get(s, 0) + 1
    overdue = [a for a in apps if a.get('follow_up_date') and a['follow_up_date'] < today and a['status'] not in ('offer', 'rejected')]
    this_week = [a for a in apps if (a.get('applied_date') or '')[:10] >= monday]
    applied_count = sum(1 for a in apps if a['status'] in ('applied', 'phone_screen', 'technical', 'onsite', 'offer', 'rejected'))
    responded = sum(1 for a in apps if a['status'] in ('phone_screen', 'technical', 'onsite', 'offer', 'rejected'))
    return {
        'total': len(apps),
        'by_stage': by_stage,
        'overdue_count': len(overdue),
        'overdue': [{'company': a['company'], 'role': a['role'], 'follow_up_date': a['follow_up_date']} for a in overdue],
        'this_week_count': len(this_week),
        'response_rate': round(responded / applied_count * 100 if applied_count else 0, 1),
    }


def get_funnel():
    """Stage-to-stage conversion across active apps. rejected counts as 'applied'
    reached (we don't store the pre-rejection stage), so rates are a floor."""
    rank = {s: i for i, s in enumerate(STAGE_ORDER)}
    apps = get_all()

    def reached_rank(a):
        st = a['status']
        if st == 'rejected':
            return rank['applied']
        return rank.get(st, 0)

    reached = [sum(1 for a in apps if reached_rank(a) >= i) for i in range(len(STAGE_ORDER))]
    steps = [{
        'from': STAGE_ORDER[i], 'to': STAGE_ORDER[i + 1],
        'reached_from': reached[i], 'reached_to': reached[i + 1],
        'rate': round(reached[i + 1] / reached[i] * 100, 1) if reached[i] else 0,
    } for i in range(len(STAGE_ORDER) - 1)]
    return {'stages': STAGE_ORDER, 'reached': reached, 'steps': steps}


# Bucket values written by older versions: "az" was the local market and "houston"
# a retired relocation target. Rows keep their stored value; reads map them here.
_BUCKET_ALIASES = {"az": "local", "houston": "other"}


def norm_bucket(b):
    b = (b or '').strip().lower() or 'other'
    return _BUCKET_ALIASES.get(b, b)


def get_cadence():
    """Weekly apps vs target, by bucket, plus the overdue-first follow-up queue."""
    from agent.config import load_settings
    s = load_settings()
    target = int(s['weekly_target'] or 0)
    bucket_targets = {}
    for k, v in (s['bucket_targets'] or {}).items():
        nk = norm_bucket(k)
        bucket_targets[nk] = bucket_targets.get(nk, 0) + (v or 0)
    apps = get_all()
    today = date.today().isoformat()
    monday = week_start()

    def bkt(a):
        return norm_bucket(a.get('bucket'))

    by_bucket, week_by_bucket = {}, {}
    for a in apps:
        b = bkt(a)
        by_bucket[b] = by_bucket.get(b, 0) + 1
        if (a.get('applied_date') or '')[:10] >= monday:
            week_by_bucket[b] = week_by_bucket.get(b, 0) + 1
    week_total = sum(v for v in week_by_bucket.values())

    needs = []
    for a in apps:
        if a['status'] in ('offer', 'rejected'):
            continue
        due = a.get('next_action_due') or a.get('follow_up_date')
        if due:
            needs.append({'id': a['id'], 'company': a['company'], 'role': a['role'],
                          'bucket': bkt(a), 'due': due[:10], 'overdue': due[:10] < today,
                          'action': a.get('next_action') or 'Follow up'})
    needs.sort(key=lambda x: (not x['overdue'], x['due']))

    # No-reply / ghosted: still sitting in "applied" with 14+ days of silence since
    # the last touch (a follow-up resets the clock via last_contacted). Auto-collected.
    two_weeks_ago = (date.today() - timedelta(days=14)).isoformat()
    no_reply = []
    for a in apps:
        if a['status'] != 'applied':
            continue
        anchor = (a.get('last_contacted') or a.get('applied_date') or '')[:10]
        if not anchor or anchor > two_weeks_ago:
            continue
        no_reply.append({'id': a['id'], 'company': a['company'], 'role': a['role'],
                         'bucket': bkt(a), 'applied_date': (a.get('applied_date') or '')[:10],
                         'since': anchor, 'days': (date.today() - date.fromisoformat(anchor)).days})
    no_reply.sort(key=lambda x: -x['days'])
    return {
        'weekly_target': target, 'bucket_targets': bucket_targets,
        'local_label': s.get('local_label') or 'Local',
        'week_total': week_total, 'week_by_bucket': week_by_bucket,
        'by_bucket': by_bucket, 'needs_followup': needs, 'no_reply': no_reply,
    }


def find_app_duplicate(company=None, role=None, url=None):
    """Active-app match by URL, else by (company, role) case-insensitively."""
    company = (company or '').strip().lower()
    role = (role or '').strip().lower()
    url = (url or '').strip().lower()
    for a in get_all():
        if url and (a.get('url') or '').strip().lower() == url:
            return a
        if company and role and (a.get('company') or '').strip().lower() == company \
                and (a.get('role') or '').strip().lower() == role:
            return a
    return None


def track_status_all(track):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM track_week_status WHERE track = ? ORDER BY week_id", [track]).fetchall()
        return {r['week_id']: dict(r) for r in rows}


def track_set_week(track, week_id, status, notes=None):
    now = _utcnow().isoformat()
    today = date.today().isoformat()
    fields = {'status': status, 'updated_at': now}
    if status == 'in_progress':
        fields['started_at'] = today
    elif status == 'completed':
        fields['completed_at'] = today
    if notes is not None:
        fields['notes'] = notes
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM track_week_status WHERE track = ? AND week_id = ?",
            [track, week_id]).fetchone()
        if existing:
            sets = ', '.join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE track_week_status SET {sets} WHERE track = ? AND week_id = ?",
                list(fields.values()) + [track, week_id])
        else:
            cols = ['track', 'week_id'] + list(fields.keys())
            placeholders = ','.join('?' for _ in cols)
            conn.execute(
                f"INSERT INTO track_week_status ({','.join(cols)}) VALUES ({placeholders})",
                [track, week_id] + list(fields.values()))


# legacy aliases — now backed by the generic track_week_status table (one source of truth)
def controls_get_all():
    return track_status_all('controls')


def controls_set_week(week_id, status, notes=None):
    track_set_week('controls', week_id, status, notes)


def ml_get_all():
    return track_status_all('ml')


def ml_set_week(week_id, status, notes=None):
    track_set_week('ml', week_id, status, notes)


def _jload(v):
    try:
        return json.loads(v or '[]')
    except (ValueError, TypeError):
        return []


def track_detail_all(track):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT week_id, objectives_done, can_explain_done, hours "
            "FROM track_progress_detail WHERE track = ?", [track]).fetchall()
        return {r['week_id']: {
            'objectives_done': _jload(r['objectives_done']),
            'can_explain_done': _jload(r['can_explain_done']),
            'hours': r['hours'] or 0,
        } for r in rows}


def track_detail_set(track, week_id, objectives_done=None, can_explain_done=None, hours=None):
    cur = track_detail_all(track).get(
        week_id, {'objectives_done': [], 'can_explain_done': [], 'hours': 0})
    obj = objectives_done if objectives_done is not None else cur['objectives_done']
    cxd = can_explain_done if can_explain_done is not None else cur['can_explain_done']
    hrs = hours if hours is not None else cur['hours']
    now = _utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO track_progress_detail "
            "(track, week_id, objectives_done, can_explain_done, hours, updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(track, week_id) DO UPDATE SET "
            "objectives_done=excluded.objectives_done, can_explain_done=excluded.can_explain_done, "
            "hours=excluded.hours, updated_at=excluded.updated_at",
            [track, week_id, json.dumps(obj), json.dumps(cxd), hrs, now])
    return {'objectives_done': obj, 'can_explain_done': cxd, 'hours': hrs}


# ── generic helpers for the consolidated tables ─────────────────────────────────

def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _rows(table, where="", params=(), order="rowid"):
    with get_conn() as conn:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order}"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _insert(table, data):
    cols = list(data.keys())
    ph = ",".join("?" for _ in cols)
    with get_conn() as conn:
        conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})", [data[c] for c in cols])
    return data


def _update(table, row_id, data):
    if not data:
        return get_row(table, row_id)
    sets = ", ".join(f"{k} = ?" for k in data)
    with get_conn() as conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", list(data.values()) + [row_id])
    return get_row(table, row_id)


def get_row(table, row_id):
    with get_conn() as conn:
        r = conn.execute(f"SELECT * FROM {table} WHERE id = ?", [row_id]).fetchone()
        return dict(r) if r else None


# ── roadmap node progress (live state over JSON-defined trees) ──────────────────
def roadmap_progress_all(roadmap_id):
    return {r["node_id"]: dict(r) for r in _rows("roadmap_progress", "roadmap_id = ?", (roadmap_id,))}


def roadmap_set_node(roadmap_id, node_id, state, notes=None):
    now = _utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO roadmap_progress (roadmap_id, node_id, state, notes, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(roadmap_id, node_id) DO UPDATE SET state = excluded.state, "
            "notes = COALESCE(excluded.notes, roadmap_progress.notes), updated_at = excluded.updated_at",
            [roadmap_id, node_id, state, notes, now])
    return {"roadmap_id": roadmap_id, "node_id": node_id, "state": state, "notes": notes, "updated_at": now}


def _delete(table, row_id):
    with get_conn() as conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", [row_id])
        return cur.rowcount > 0


# ── day blocks (hour-by-hour plan) ──────────────────────────────────────────────
_BLOCK_COLS = ("date", "start", "end", "cat", "title", "detail", "deep_link",
               "source_kind", "source_id", "status", "actual_min", "gcal_event_id", "pos")


def day_blocks_for(day):
    return _rows("day_blocks", "date = ?", (day,), order="start, pos")


def day_blocks_range(start, end):
    return _rows("day_blocks", "date >= ? AND date <= ?", (start, end), order="date, start, pos")


def day_block_create(d):
    row = {k: d.get(k) for k in _BLOCK_COLS if k in d}
    row.setdefault("status", "planned")
    row.setdefault("actual_min", 0)
    row.setdefault("pos", 0)
    row["id"] = _new_id("blk")
    row["updated_at"] = _utcnow().isoformat()
    return _insert("day_blocks", row)


def day_block_update(bid, d):
    patch = {k: v for k, v in d.items() if k in _BLOCK_COLS}
    if not patch:
        return get_row("day_blocks", bid)
    patch["updated_at"] = _utcnow().isoformat()
    return _update("day_blocks", bid, patch)


def day_block_delete(bid):
    return _delete("day_blocks", bid)


def day_blocks_clear(day, keep_done=True):
    with get_conn() as conn:
        if keep_done:
            conn.execute("DELETE FROM day_blocks WHERE date = ? AND status != 'done'", [day])
        else:
            conn.execute("DELETE FROM day_blocks WHERE date = ?", [day])


# ── profile links checklist ─────────────────────────────────────────────────────
def links_all():
    out = []
    for r in _rows("profile_links", order="sort, rowid"):
        r["checklist"] = _jload(r.get("checklist")) or []
        out.append(r)
    return out


def link_update(lid, d):
    patch = {k: v for k, v in d.items() if k in ("url", "status", "due", "notes", "label")}
    if "checklist" in d and isinstance(d["checklist"], list):
        patch["checklist"] = json.dumps(d["checklist"])
    if not patch:
        r = get_row("profile_links", lid)
    else:
        patch["updated_at"] = _utcnow().isoformat()
        r = _update("profile_links", lid, patch)
    if r:
        r["checklist"] = _jload(r.get("checklist")) or []
    return r


# ── project inventory ───────────────────────────────────────────────────────────
_PROJECT_COLS = ("slug", "name", "tier", "path", "category", "stack", "status", "role",
                 "started", "ended", "repo_url", "demo_url", "purpose", "problem",
                 "built", "decision", "result", "differently", "pitch", "sort", "ship")

# Mirrors the keys in projects.SHIP_ITEMS. Duplicated here rather than imported
# because projects.py imports db — importing projects from db would be circular.
_SHIP_KEYS = ("repo", "readme", "demo", "bullet", "portfolio")


def projects_all():
    return _rows("projects", order="sort, rowid")


def project_get(pid):
    return get_row("projects", pid)


def project_add(d):
    row = {k: v for k, v in d.items() if k in _PROJECT_COLS}
    row["id"] = _new_id("proj")
    row.setdefault("slug", row["id"])
    row["updated_at"] = _utcnow().isoformat()
    _insert("projects", row)
    return get_row("projects", row["id"])


def project_update(pid, d):
    d = dict(d)
    if "ship" in d:
        if isinstance(d["ship"], dict):
            d["ship"] = json.dumps({k: bool(d["ship"].get(k)) for k in _SHIP_KEYS})
        else:
            d.pop("ship")
    patch = {k: v for k, v in d.items() if k in _PROJECT_COLS}
    if not patch:
        return get_row("projects", pid)
    patch["updated_at"] = _utcnow().isoformat()
    return _update("projects", pid, patch)


def project_delete(pid):
    return _delete("projects", pid)


# ── side revenue / clips log ────────────────────────────────────────────────────
def side_all(limit=None):
    rows = _rows("side_log", order="date DESC, created_at DESC")
    return rows[:limit] if limit else rows


def side_create(d):
    row = {"id": _new_id("side"), "date": d.get("date") or date.today().isoformat(),
           "source": d.get("source") or "clips", "platform": d.get("platform"),
           "posts": int(d.get("posts") or 0), "followers": int(d.get("followers") or 0),
           "views": int(d.get("views") or 0), "revenue": float(d.get("revenue") or 0),
           "note": d.get("note")}
    return _insert("side_log", row)


def side_delete(sid):
    return _delete("side_log", sid)


def side_summary(today=None):
    """Latest followers per platform, posts/revenue month-to-date and total,
    posting streak (consecutive days with ≥1 post, ending today or yesterday)."""
    today = today or date.today()
    rows = side_all()
    month = today.strftime("%Y-%m")
    latest = {}
    for r in rows:  # rows are newest-first
        p = r.get("platform") or "—"
        if p not in latest and (r.get("followers") or 0):
            latest[p] = {"followers": r["followers"], "date": r["date"]}
    posts_mtd = sum(r["posts"] or 0 for r in rows if (r["date"] or "").startswith(month))
    rev_mtd = round(sum(r["revenue"] or 0 for r in rows if (r["date"] or "").startswith(month)), 2)
    posts_total = sum(r["posts"] or 0 for r in rows)
    rev_total = round(sum(r["revenue"] or 0 for r in rows), 2)
    post_days = {r["date"] for r in rows if (r["posts"] or 0) > 0}
    streak, d = 0, today
    if d.isoformat() not in post_days:
        d = d - timedelta(days=1)
    while d.isoformat() in post_days:
        streak += 1
        d -= timedelta(days=1)
    return {"latest_followers": latest, "posts_mtd": posts_mtd, "revenue_mtd": rev_mtd,
            "posts_total": posts_total, "revenue_total": rev_total, "streak_days": streak,
            "entries": len(rows)}


# ── personal health (weigh-ins, workout log, daily routine) ─────────────────────
def health_days(limit=None, since=None):
    rows = _rows("health_day", *(("date >= ?", (since,)) if since else ("", ())), order="date DESC")
    for r in rows:
        r["routine"] = _jload(r.get("routine")) or {}
    return rows[:limit] if limit else rows


def health_day_get(day):
    rows = _rows("health_day", "date = ?", (day,))
    if not rows:
        return None
    rows[0]["routine"] = _jload(rows[0].get("routine")) or {}
    return rows[0]


def health_day_upsert(day, d):
    """One row per date. Only the keys present in `d` are written, so logging a
    weigh-in never clears that day's workout."""
    patch = {}
    if "weight_lb" in d:
        patch["weight_lb"] = float(d["weight_lb"]) if d["weight_lb"] not in (None, "") else None
    if "split" in d:
        patch["split"] = d["split"] or None
    if "minutes" in d:
        patch["minutes"] = int(d["minutes"] or 0)
    if "routine" in d:
        patch["routine"] = json.dumps(d["routine"] or {})
    if "note" in d:
        patch["note"] = d["note"] or None
    patch["updated_at"] = _utcnow().isoformat()
    cur = _rows("health_day", "date = ?", (day,))
    if cur:
        _update("health_day", cur[0]["id"], patch)
    else:
        _insert("health_day", {"id": _new_id("hd"), "date": day, **patch})
    return health_day_get(day)


def workouts_all(split=None):
    return _rows("workouts", *(("split = ?", (split,)) if split else ("", ())),
                 order="split, sort, rowid")


def workout_create(d):
    return _insert("workouts", {
        "id": _new_id("wo"), "split": (d.get("split") or "push").strip().lower(),
        "name": (d.get("name") or "").strip(), "sets": d.get("sets"),
        "note": d.get("note"), "sort": int(d.get("sort") or 0)})


def workout_update(wid, d):
    patch = {k: d[k] for k in ("split", "name", "sets", "note", "sort") if k in d}
    if "split" in patch:
        patch["split"] = (patch["split"] or "push").strip().lower()
    if "sort" in patch:
        patch["sort"] = int(patch["sort"] or 0)
    patch["updated_at"] = _utcnow().isoformat()
    return _update("workouts", wid, patch)


def workout_delete(wid):
    return _delete("workouts", wid)


# milestones
def milestones_all():
    return _rows("milestones", order="sort, rowid")

def milestone_create(d):
    return _insert("milestones", {
        "id": _new_id("ms"), "phase": d.get("phase", 1), "text": d["text"],
        "due": d.get("due"), "done": int(bool(d.get("done"))), "sort": d.get("sort", 0)})

def milestone_update(mid, d):
    return _update("milestones", mid, {k: v for k, v in d.items() if k in
                   ("phase", "text", "due", "done", "sort")})

def milestone_toggle(mid):
    m = get_row("milestones", mid)
    if not m:
        return None
    return _update("milestones", mid, {"done": 0 if m["done"] else 1})

def milestone_delete(mid):
    return _delete("milestones", mid)


# weekly_actions
def weekly_all(week=None):
    return _rows("weekly_actions", "week = ?" if week else "",
                 (week,) if week else (), order="sort, rowid")

def weekly_create(d):
    return _insert("weekly_actions", {
        "id": _new_id("wa"), "week": d["week"], "text": d["text"],
        "done": int(bool(d.get("done"))), "sort": d.get("sort", 0)})

def weekly_toggle(wid):
    w = get_row("weekly_actions", wid)
    if not w:
        return None
    return _update("weekly_actions", wid, {"done": 0 if w["done"] else 1})

def weekly_delete(wid):
    return _delete("weekly_actions", wid)


# skill_gaps
def skills_all():
    return _rows("skill_gaps", order="sort, rowid")

def skill_create(d):
    evidence = d.get("evidence")
    profiles = d.get("related_profiles")
    return _insert("skill_gaps", {
        "id": _new_id("sg"), "skill": d["skill"], "priority": d.get("priority"),
        "target_hours": d.get("target_hours", 0), "hours_logged": d.get("hours_logged", 0),
        "complete": int(bool(d.get("complete"))),
        "proficiency": int(d.get("proficiency") or 0),
        "target_proficiency": int(d.get("target_proficiency") or 0),
        "evidence": evidence if isinstance(evidence, str) else json.dumps(evidence or []),
        "domain": d.get("domain"), "related_track": d.get("related_track"),
        "related_profiles": profiles if isinstance(profiles, str) else json.dumps(profiles or []),
        "sort": d.get("sort", 0)})

def skill_log_hours(sid, hours):
    s = get_row("skill_gaps", sid)
    if not s:
        return None
    return _update("skill_gaps", sid, {"hours_logged": (s["hours_logged"] or 0) + hours})

def skill_update(sid, d):
    d = dict(d)
    for k in ("evidence", "related_profiles"):  # accept arrays or pre-encoded JSON
        if k in d and not isinstance(d[k], str):
            d[k] = json.dumps(d[k] or [])
    return _update("skill_gaps", sid, {k: v for k, v in d.items() if k in
                   ("skill", "priority", "target_hours", "hours_logged", "complete", "sort",
                    "proficiency", "target_proficiency", "evidence", "domain",
                    "related_track", "related_profiles")})

def skill_delete(sid):
    return _delete("skill_gaps", sid)


# certifications
def _norm_steps(v):
    if isinstance(v, str):
        v = _jload(v)
    out = []
    for s in v if isinstance(v, list) else []:
        if not isinstance(s, dict) or not str(s.get("text") or "").strip():
            continue
        try:
            hours = float(s.get("hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        out.append({"text": str(s["text"]).strip(), "hours": hours, "done": bool(s.get("done"))})
    return out


def _cert_out(r):
    if not r:
        return r
    r["steps"] = _norm_steps(r.get("steps"))
    try:
        h = json.loads(r["how_to"]) if r.get("how_to") else None
    except (TypeError, ValueError):
        h = None
    r["how_to"] = h if isinstance(h, dict) else None
    return r


def cert_get(cid):
    return _cert_out(get_row("certifications", cid))


def cert_seed_fields(cid, d):
    patch = {k: v for k, v in d.items()
             if k in ("verdict", "verdict_reason", "cost_usd", "status", "exam_date")}
    if "how_to" in d:
        patch["how_to"] = json.dumps(d["how_to"]) if d["how_to"] is not None else None
    if "steps" in d:
        patch["steps"] = json.dumps(_norm_steps(d["steps"]))
    patch["updated_at"] = _utcnow().isoformat()
    return _cert_out(_update("certifications", cid, patch))


def certs_all(track=None, status=None):
    where, params = [], []
    if track:
        where.append("track = ?"); params.append(track)
    if status:
        where.append("status = ?"); params.append(status)
    return [_cert_out(r) for r in _rows("certifications", " AND ".join(where), tuple(params), order="sort, rowid")]

def cert_create(d):
    skills, profiles = d.get("related_skills"), d.get("related_profiles")
    return _cert_out(_insert("certifications", {
        "id": _new_id("cert"), "provider": d.get("provider"), "title": d["title"],
        "url": d.get("url"), "track": d.get("track", "general"),
        "category": d.get("category"), "time_est": d.get("time_est"), "why": d.get("why"),
        "status": d.get("status", "wishlist"), "hours": d.get("hours"),
        "cost": d.get("cost"), "cost_usd": d.get("cost_usd"), "exam_date": d.get("exam_date"),
        "related_skills": skills if isinstance(skills, str) else json.dumps(skills or []),
        "related_profiles": profiles if isinstance(profiles, str) else json.dumps(profiles or []),
        "notes": d.get("notes"), "sort": d.get("sort", 0),
        "steps": json.dumps(_norm_steps(d.get("steps") or [])),
        "created_at": _utcnow().isoformat()}))

def cert_update(cid, d):
    d = dict(d)
    for k in ("related_skills", "related_profiles"):  # accept arrays or pre-encoded JSON
        if k in d and not isinstance(d[k], str):
            d[k] = json.dumps(d[k] or [])
    if "steps" in d:
        d["steps"] = json.dumps(_norm_steps(d["steps"]))
    d = {k: v for k, v in d.items() if k in
         ("provider", "title", "url", "track", "status", "hours", "cost", "notes",
          "category", "time_est", "why", "sort", "related_skills", "related_profiles",
          "exam_date", "cost_usd", "steps")}
    d["updated_at"] = _utcnow().isoformat()
    return _cert_out(_update("certifications", cid, d))

def cert_delete(cid):
    return _delete("certifications", cid)


# timeline_events
def timeline_all(track=None, phase=None):
    where, params = [], []
    if track:
        where.append("track = ?"); params.append(track)
    if phase:
        where.append("phase = ?"); params.append(phase)
    return _rows("timeline_events", " AND ".join(where), tuple(params), order="date")

def timeline_create(d):
    return _insert("timeline_events", {
        "id": _new_id("tl"), "date": d["date"], "kind": d.get("kind", "milestone"),
        "label": d["label"], "phase": d.get("phase"), "track": d.get("track"),
        "done": int(bool(d.get("done"))), "notes": d.get("notes"),
        "updated_at": _utcnow().isoformat()})

def timeline_update(eid, d):
    fields = {k: v for k, v in d.items() if k in
              ("date", "kind", "label", "phase", "track", "done", "notes")}
    fields["updated_at"] = _utcnow().isoformat()  # audit: trace silent date changes
    return _update("timeline_events", eid, fields)

def timeline_delete(eid):
    return _delete("timeline_events", eid)


# notes
def notes_all(limit=None):
    rows = _rows("notes", order="pinned DESC, ts DESC")
    return rows[:limit] if limit else rows

def note_create(text):
    ts = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return _insert("notes", {"id": _new_id("note"), "ts": ts, "text": text, "edited": None, "pinned": 0})

def note_update(nid, text=None, pinned=None):
    fields = {}
    if text is not None:
        fields["text"] = text
        fields["edited"] = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if pinned is not None:
        fields["pinned"] = int(bool(pinned))
    if not fields:
        return get_row("notes", nid)
    return _update("notes", nid, fields)

def note_delete(nid):
    return _delete("notes", nid)


# reminders
def reminders_open():
    return _rows("reminders", "dismissed = 0", order="created_at DESC")

def reminder_upsert(d):
    """Idempotent by (kind, ref_type, ref_id, due) so the notifier can re-run safely.
    `followup_missing` nags dedupe on (kind, ref_type, ref_id) alone — their due
    is always 'today', which would otherwise resurrect dismissed nags daily."""
    with get_conn() as conn:
        if d.get("kind") == "followup_missing":
            existing = conn.execute(
                "SELECT id FROM reminders WHERE kind IS ? AND ref_type IS ? AND ref_id IS ?",
                (d.get("kind"), d.get("ref_type"), d.get("ref_id"))).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM reminders WHERE kind IS ? AND ref_type IS ? AND ref_id IS ? AND due IS ?",
                (d.get("kind"), d.get("ref_type"), d.get("ref_id"), d.get("due"))).fetchone()
        if existing:
            return existing["id"]
    rec = {"id": _new_id("rem"), "kind": d["kind"], "title": d["title"],
           "body": d.get("body"), "due": d.get("due"), "ref_type": d.get("ref_type"),
           "ref_id": d.get("ref_id"), "read": 0, "dismissed": 0}
    _insert("reminders", rec)
    return rec["id"]

def reminder_mark(rid, *, read=None, dismissed=None):
    d = {}
    if read is not None:
        d["read"] = int(read)
    if dismissed is not None:
        d["dismissed"] = int(dismissed)
    return _update("reminders", rid, d)

