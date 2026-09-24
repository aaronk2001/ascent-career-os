from datetime import datetime
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

import db
from dayplan import CATS

SECRETS_DIR = Path(__file__).parent / ".secrets"
CLIENT_SECRET = SECRETS_DIR / "client_secret.json"
TOKEN = SECRETS_DIR / "token.json"
CALENDAR_ID_CACHE = SECRETS_DIR / "calendar_id.txt"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_NAME = "Ascent"


def _tz_offset():
    """This machine's current UTC offset as RFC3339 "+HH:MM". Events are written
    with an explicit offset, so no IANA zone name (or tzdata on Windows) is needed."""
    z = datetime.now().astimezone().strftime("%z")
    return f"{z[:3]}:{z[3:]}"

_COLOR_BY_CAT = {
    "apps": "9", "controls": "7", "ml": "3", "outreach": "5",
    "clips": "4", "portfolio": "2", "review": "8", "bridge": "10",
}


@lru_cache(maxsize=1)
def _libs_installed():
    """Are the Google libs importable? `find_spec` only stats the path — actually
    importing google_auth_oauthlib took ~24s on a Microsoft Store Python install,
    far too slow for a status probe.
    """
    try:
        return all(find_spec(m) for m in ("google_auth_oauthlib", "googleapiclient"))
    except (ImportError, ValueError):
        return False


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("calendar", "v3", credentials=creds)


def _calendar_id(service):
    if CALENDAR_ID_CACHE.exists():
        cid = CALENDAR_ID_CACHE.read_text(encoding="utf-8").strip()
        if cid:
            return cid
    page_token = None
    while True:
        resp = service.calendarList().list(pageToken=page_token).execute()
        for cal in resp.get("items", []):
            if cal.get("summary") == CALENDAR_NAME:
                CALENDAR_ID_CACHE.write_text(cal["id"], encoding="utf-8")
                return cal["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    created = service.calendars().insert(body={"summary": CALENDAR_NAME}).execute()
    CALENDAR_ID_CACHE.write_text(created["id"], encoding="utf-8")
    return created["id"]


def status():
    libs = _libs_installed()
    connected, calendar_id, error = False, None, None
    if libs and TOKEN.exists():
        try:
            service = _service()
            calendar_id = _calendar_id(service)
            connected = True
        except Exception as e:
            error = str(e)
    return {"connected": connected, "has_client_secret": CLIENT_SECRET.exists(),
            "libs_installed": libs, "calendar_id": calendar_id, "error": error}


def connect():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        if TOKEN.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN.write_text(creds.to_json(), encoding="utf-8")
            if creds.valid:
                return status()
        if not CLIENT_SECRET.exists():
            return {"ok": False, "error": f"missing {CLIENT_SECRET}"}
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        return status()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _delete_orphans(service, calendar_id, iso, keep_ids):
    deleted = 0
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id, timeMin=f"{iso}T00:00:00{_tz_offset()}",
            timeMax=f"{iso}T23:59:59{_tz_offset()}",
            singleEvents=True, pageToken=page_token).execute()
        for ev in resp.get("items", []):
            if ev["id"] in keep_ids or not (ev.get("summary") or "").startswith("["):
                continue
            service.events().delete(calendarId=calendar_id, eventId=ev["id"]).execute()
            deleted += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return deleted


def _event_body(b, iso):
    off = _tz_offset()
    detail = b.get("detail") or ""
    if b.get("deep_link"):
        detail += f"\n{b['deep_link']}"
    return {
        "summary": f"[{CATS.get(b['cat'], {}).get('label', b['cat'])}] {b['title']}",
        "description": detail,
        "start": {"dateTime": f"{iso}T{b['start']}:00{off}"},
        "end": {"dateTime": f"{iso}T{b['end']}:00{off}"},
        "colorId": _COLOR_BY_CAT.get(b["cat"]),
    }


def sync_day(day):
    iso = day.isoformat() if hasattr(day, "isoformat") else str(day)[:10]
    try:
        service = _service()
        calendar_id = _calendar_id(service)
        blocks = [b for b in db.day_blocks_for(iso) if b["cat"] != "break"]
        kept_ids, synced = set(), 0
        for b in blocks:
            body = _event_body(b, iso)
            ev = None
            if b.get("gcal_event_id"):
                try:
                    ev = service.events().update(
                        calendarId=calendar_id, eventId=b["gcal_event_id"], body=body).execute()
                except Exception as e:
                    if "404" not in str(e):
                        raise
            if ev is None:
                ev = service.events().insert(calendarId=calendar_id, body=body).execute()
                db.day_block_update(b["id"], {"gcal_event_id": ev["id"]})
            kept_ids.add(ev["id"])
            synced += 1
        deleted = _delete_orphans(service, calendar_id, iso, kept_ids)
        return {"synced": synced, "deleted": deleted, "date": iso}
    except Exception as e:
        return {"ok": False, "error": str(e)}
