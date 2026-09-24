# Google Calendar Push Setup

Ascent's Today view can push the day's blocks into a dedicated Google Calendar so they show up
on your phone. The sync is **one-way**: Ascent writes events, Google Calendar never writes back.
Re-pushing a day updates its existing events in place (matched via `gcal_event_id` on each block)
rather than duplicating them.

## Setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project
   named `Ascent`.
2. In that project, go to **APIs & Services → Library** and enable the **Google Calendar API**.
3. Go to **APIs & Services → OAuth consent screen**. Choose **External**, set publishing status to
   **Testing**, and add your own Google account as a test user.
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**. Choose
   application type **Desktop app**.
5. Download the resulting JSON.
6. Save it as `career-planner/.secrets/client_secret.json` (create the `.secrets/` folder if it
   doesn't exist — it's gitignored).
7. Install the Google client libraries into the same Python that runs Ascent:
   `pip install google-api-python-client google-auth-oauthlib`.
8. Open Ascent, go to **Today**, and click **Connect Google Calendar**.
9. A browser window opens for the Google OAuth consent screen — approve access. Ascent saves the
   resulting token to `.secrets/token.json`.
10. Click **Push to Calendar**. Ascent creates (or reuses) a calendar named **Ascent** in your
    Google account and writes that day's blocks into it — visible on your phone's Calendar app
    once it syncs.
