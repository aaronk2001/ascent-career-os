# Google Calendar Push Setup (API only)

Ascent can push a day's goal blocks into a dedicated Google Calendar so they show up on your
phone. The sync is **one-way**: Ascent writes events, Google Calendar never writes back.
Re-pushing a day updates its existing events in place (matched via `gcal_event_id` on each block)
rather than duplicating them. Events are written with this machine's current UTC offset.

**There is no button for this in the UI yet.** The feature is three API routes, called with
`curl` (or from a script / scheduled task) while Ascent is running on port 5001:

| Route | Does |
|---|---|
| `GET /api/gcal/status` | Libraries installed? Client secret present? Connected? |
| `POST /api/gcal/connect` | Runs the OAuth flow in your browser and saves the token |
| `POST /api/day/sync-gcal` | Pushes one day's blocks; body `{"date": "YYYY-MM-DD"}` (default today) |

## Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project
   named `Ascent`.
2. In that project, go to **APIs & Services → Library** and enable the **Google Calendar API**.
3. Go to **APIs & Services → OAuth consent screen**. Choose **External**, set publishing status to
   **Testing**, and add your own Google account as a test user.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**. Choose
   application type **Desktop app**.
5. Download the resulting JSON.
6. Save it as `.secrets/client_secret.json` in the repo root (create the `.secrets/` folder if it
   doesn't exist; it's gitignored).
7. Install the optional Google client libraries into the venv that runs Ascent:
   `pip install -r requirements-optional.txt` (or just the three `google-*` lines from it).
8. Connect once. A browser window opens for the Google OAuth consent screen; approve access and
   Ascent saves the token to `.secrets/token.json`:

   ```bash
   curl -X POST http://127.0.0.1:5001/api/gcal/connect
   ```

9. Push a day. Ascent creates (or reuses) a calendar named **Ascent** in your Google account and
   writes that day's blocks into it:

   ```bash
   curl -X POST http://127.0.0.1:5001/api/day/sync-gcal -H "Content-Type: application/json" -d "{}"
   ```
