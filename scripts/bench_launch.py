"""Cold-launch bench for Ascent.

Times the imports that dominate startup and every endpoint the Today view
blocks on. Run with the backend already serving (python tracker.py), e.g.

    python scripts/bench_launch.py --port 5000

Always hits 127.0.0.1: Flask binds IPv4-only, so `localhost` costs a ~2s
IPv6 connect-fail per request and makes every endpoint look slow.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IMPORTS = ["flask", "yaml", "dotenv", "webview", "google_auth_oauthlib", "tracker"]
ENDPOINTS = ["/", "/api/day", "/api/day/week", "/api/anchors", "/api/gcal/status",
             "/api/reminders", "/api/schedule"]


def time_import(mod):
    t = time.perf_counter()
    p = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=str(ROOT),
                       capture_output=True, text=True)
    dt = (time.perf_counter() - t) * 1000
    return dt, (p.stderr.strip().splitlines()[-1] if p.returncode else "")


def time_get(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            n = len(r.read())
        return (time.perf_counter() - t) * 1000, n, ""
    except Exception as e:
        return (time.perf_counter() - t) * 1000, 0, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--skip-imports", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = {"imports": {}, "endpoints": {}}

    if not args.skip_imports:
        print("== imports (fresh interpreter each) ==")
        for m in IMPORTS:
            dt, err = time_import(m)
            out["imports"][m] = round(dt)
            print(f"  {m:24s} {dt:9.0f} ms{'  FAILED: ' + err if err else ''}")

    print(f"\n== endpoints (127.0.0.1:{args.port}) ==")
    for p in ENDPOINTS:
        dt, n, err = time_get(args.port, p)
        out["endpoints"][p] = round(dt)
        print(f"  {p:24s} {dt:9.0f} ms  {n:7d} B{'  ERR: ' + err if err else ''}")

    print("\n== endpoints, second hit (warm caches) ==")
    for p in ENDPOINTS:
        dt, n, err = time_get(args.port, p)
        out["endpoints"][p + " (warm)"] = round(dt)
        print(f"  {p:24s} {dt:9.0f} ms{'  ERR: ' + err if err else ''}")

    if args.json:
        print("\n" + json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
