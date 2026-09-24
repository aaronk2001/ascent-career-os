"""
Ascent desktop entry point. Starts Flask in a background thread, then opens the
UI (127.0.0.1:5001) in a native pywebview window.

    python app.py             # your data (career.db, settings.yaml, profile.yaml)
    python app.py --demo      # fictional demo data in demo/ on port 5002 (seeded on first run)
    python app.py --browser   # no native window: serve and open the system browser
    python app.py --browser --no-open   # serve only (headless checks, remote shells)
    python app.py --dev       # window on the Vite dev server (HMR)
"""
import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# NB: `import webview` and `from tracker import app` are deferred (not at module
# top) so they can run concurrently — webview on the main thread, tracker inside
# the Flask thread — instead of serializing ~webview + ~tracker import time. The
# reuse path also skips the tracker import entirely. See __main__ below.

HERE = Path(__file__).parent
PORT = int(os.environ.get("ASCENT_PORT") or 5001)
DEMO_PORT = 5002
VITE_PORT = 5173
FRONTEND_DIR = HERE / "frontend"

# Dev mode (`python app.py --dev`) points the window at the Vite dev server for
# live reload / HMR — edit frontend/src and the window updates with no rebuild.
DEV = "--dev" in sys.argv or os.environ.get("ASCENT_DEV") == "1"
DEMO = "--demo" in sys.argv
# Serve + system browser instead of pywebview: for Linux boxes without the GTK/Qt
# bindings pywebview needs, and for headless checks.
BROWSER = "--browser" in sys.argv
NO_OPEN = "--no-open" in sys.argv
_OVERRIDES = ("ASCENT_DB", "ASCENT_SETTINGS", "ASCENT_PROFILE", "TRACKER_DATA", "ASCENT_SCHEDULE")


def _use_demo():
    """Point every data path at demo/ (seeding it on first use) before tracker is imported."""
    sys.path.insert(0, str(HERE / "scripts"))
    import seed_demo
    out = HERE / "demo"
    if not (out / "career.db").exists():
        print("Seeding the demo instance into demo/ ...")
        seed_demo.build(out)
    os.environ.update(seed_demo.demo_env(out))


def _db_path():
    return Path(os.environ.get("ASCENT_DB") or HERE / "career.db").resolve()


def _reusable(port):
    """True if the backend on `port` is Ascent serving this same database. Backends
    from before /api/instance existed are reused only when no path override is set."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/instance", timeout=2) as r:
            return Path(json.load(r)["db"]).resolve() == _db_path()
    except urllib.error.HTTPError as e:
        return e.code == 404 and not DEMO and not any(os.environ.get(k) for k in _OVERRIDES)
    except Exception:
        return False


def _find_bun():
    found = shutil.which("bun")
    if found:
        return found
    cand = Path.home() / ".bun" / "bin" / ("bun.exe" if os.name == "nt" else "bun")
    return str(cand) if cand.exists() else None


def _start_vite(api_port):
    """Launch the Vite dev server, proxying /api to this backend's port; returns
    the Popen so we can kill it on exit."""
    bun = _find_bun()
    if not bun:
        raise SystemExit("Ascent --dev needs bun, which wasn't found on PATH or in ~/.bun.")
    proc = subprocess.Popen([bun, "run", "dev"], cwd=str(FRONTEND_DIR),
                            env={**os.environ, "ASCENT_API_PORT": str(api_port)})
    atexit.register(lambda: proc.terminate())
    return proc

# Evergreen WebView2 bootstrapper (Microsoft first-party).
WEBVIEW2_DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def _webview2_installed():
    """True if the Edge WebView2 runtime pywebview needs is present on Windows."""
    if os.name != "nt":
        return True
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft" / "EdgeWebView" / "Application",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft" / "EdgeWebView" / "Application",
    ]
    return any(p.is_dir() and any(p.iterdir()) for p in candidates)


def _warn_missing_webview2():
    """Surface the missing-runtime cause instead of crashing silently under pythonw."""
    msg = (
        "Ascent needs the Microsoft Edge WebView2 Runtime, which isn't installed.\n\n"
        "Install it with:\n"
        "    winget install Microsoft.EdgeWebView2Runtime\n\n"
        "Or download the runtime in the browser that will now open, then relaunch Ascent."
    )
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "Ascent — WebView2 required", 0x10)
    except Exception:
        print(msg)
    try:
        webbrowser.open(WEBVIEW2_DOWNLOAD)
    except Exception:
        pass


def _start_flask(port):
    # tracker imported here (not at module top) so its ~import cost runs inside
    # this thread, overlapping `import webview` on the main thread.
    from tracker import app as flask_app
    flask_app.config["ASCENT_PORTS"] = {port}  # tracker's Host/Origin guard
    # threaded=True so the dashboard's ~11 concurrent API calls run in parallel
    # instead of serializing on the single-threaded dev server.
    flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


def _prewarm():
    """Parse the slow YAML caches (glossary ~7.6s cold, track files) up front in a
    daemon thread so the cost hides behind WebView2 startup instead of stalling
    the first dashboard paint."""
    try:
        # Track yaml first: /api/day and /api/anchors both block on it, and Today
        # is the default route. Glossary and news belong to Dashboard/Glossary, so
        # they wait — this thread contends with the Flask thread for the GIL.
        import registry
        for tid in registry.track_ids():
            registry.load_track(tid)
        time.sleep(2)
        import glossary
        glossary.as_list()
        # Warm the news cache (3 RSS fetches) so the dashboard's Signal widget
        # has hot data instead of paying the network round-trip on first mount.
        import news
        if news.enabled():
            news.get_news(list(news.DEFAULT_TOPICS))
    except Exception:
        pass


def _wait_for_port(port, timeout=45):
    """Block until localhost:port accepts connections, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _http_ok(port, timeout=2):
    """True only if an Ascent backend actually answers HTTP 200 on this port.
    A raw TCP connect isn't enough: a dead/orphaned WebView2 child can keep the
    port in LISTENING state without serving, which is what wedged old launches."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _port_busy(port):
    """True if anything is listening on the port (healthy backend OR a zombie)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _free_port():
    """Ask the OS for an unused port to sidestep a wedged one."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_health(port, timeout=30):
    """Block until the backend answers HTTP 200, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _http_ok(port, timeout=1):
            return True
        time.sleep(0.1)
    return False


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(HERE / ".env")  # same overrides tracker.py will see
    except ImportError:
        pass
    if DEMO:
        _use_demo()
    want = DEMO_PORT if DEMO else PORT

    if BROWSER:
        port = want if not _port_busy(want) else _free_port()
        url = f"http://127.0.0.1:{port}"
        print(f"Ascent{' (demo)' if DEMO else ''}: {url}  (Ctrl+C to stop)")
        if not NO_OPEN:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        _start_flask(port)
        raise SystemExit(0)

    if not _webview2_installed():
        _warn_missing_webview2()
        raise SystemExit(1)

    # Re-launching Ascent (double-clicking the shortcut again) must not pile up
    # duplicate Flask+WebView2 instances. On Windows that wedges port 5001
    # (SO_REUSEADDR lets dead instances keep holding it) and the new window ends
    # up pointed at a non-responding backend — the blank "won't load" symptom.
    # So: reuse a healthy backend if one is already serving the same database;
    # otherwise start our own, picking a free port if the port is taken (a zombie,
    # or an instance serving other data). Always start fresh in --dev.
    if not DEV and _http_ok(want) and _reusable(want):
        port = want
        import webview  # reuse path: no tracker import needed at all
    else:
        port = want if not _port_busy(want) else _free_port()
        threading.Thread(target=_start_flask, args=(port,), daemon=True).start()
        threading.Thread(target=_prewarm, daemon=True).start()
        import webview  # overlaps the tracker import running in the Flask thread
        if not _wait_for_health(port, timeout=30):
            msg = (f"Ascent's backend did not become healthy on port {port} in 30s.\n\n"
                   "A Python error likely occurred — run `python app.py` from a "
                   "console in the repo folder to see it.")
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "Ascent — startup failed", 0x10)
            except Exception:
                print(msg)
            raise SystemExit(1)

    url = f"http://127.0.0.1:{port}"
    if DEV:
        _start_vite(port)
        if not _wait_for_port(VITE_PORT, timeout=30):
            print(f"Vite dev server did not start on port {VITE_PORT}.")
            raise SystemExit(1)
        url = f"http://127.0.0.1:{VITE_PORT}"

    icon = str(Path(__file__).parent / "ascent.ico")

    # Ascent window
    window1 = webview.create_window(
        title="Ascent (dev)" if DEV else "Ascent (demo)" if DEMO else "Ascent",
        url=url,
        width=1440,
        height=900,
        resizable=True,
        maximized=True,
        min_size=(900, 600),
    )

    webview.start(icon=icon)
