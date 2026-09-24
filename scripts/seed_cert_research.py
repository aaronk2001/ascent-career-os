"""Seed cert verdicts / how-to / study steps from scripts/cert_research_seed.json.

Dry-run by default; --apply backs up career.db then writes. Idempotent: verdict/how_to
are overwritten from the file, steps are only seeded when a cert has none (so ticked
progress survives), new certs are matched by title. Never changes an existing status.
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

SEED = Path(__file__).with_name("cert_research_seed.json")


def run(seed, apply):
    rows = {c["id"]: c for c in db.certs_all()}
    unknown = [i for i in seed["verdicts"] if i not in rows] + [i for i in seed["keepers"] if i not in rows]
    if unknown:
        raise ValueError(f"unknown cert ids in seed: {sorted(set(unknown))}")
    log = []
    for cid, v in seed["verdicts"].items():
        patch = {"verdict": v["verdict"], "verdict_reason": v.get("reason")}
        k = seed["keepers"].get(cid)
        if k:
            patch["how_to"] = k.get("how_to")
            if k.get("cost_usd") is not None:
                patch["cost_usd"] = k["cost_usd"]
            if not rows[cid]["steps"]:
                patch["steps"] = k.get("steps") or []
        log.append(f"{cid} {rows[cid]['title'][:40]!r}: {v['verdict']}"
                   + (f" +how_to +{len(patch.get('steps', []))} steps" if k else ""))
        if apply:
            db.cert_seed_fields(cid, patch)
    by_title = {c["title"]: c for c in rows.values()}
    for n in seed.get("new", []):
        existing = by_title.get(n["title"])
        if existing:
            log.append(f"exists {n['title']!r} — refresh verdict/how_to")
            if apply:
                patch = {"verdict": n["verdict"], "verdict_reason": n.get("reason"), "how_to": n.get("how_to")}
                if n.get("cost_usd") is not None:
                    patch["cost_usd"] = n["cost_usd"]
                if not existing["steps"]:
                    patch["steps"] = n.get("steps") or []
                db.cert_seed_fields(existing["id"], patch)
            continue
        log.append(f"new {n['title']!r}: {n['verdict']}")
        if apply:
            c = db.cert_create({"title": n["title"], "provider": n.get("provider"),
                                "track": n.get("track", "phase1"), "status": "wishlist",
                                "cost_usd": n.get("cost_usd")})
            db.cert_seed_fields(c["id"], {"verdict": n["verdict"], "verdict_reason": n.get("reason"),
                                          "how_to": n.get("how_to"), "steps": n.get("steps") or []})
    return log


def main():
    apply = "--apply" in sys.argv
    if apply:
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        shutil.copy2(db.DB_PATH, f"{db.DB_PATH}.bak-cert-seed-{stamp}")
    for line in run(json.loads(SEED.read_text(encoding="utf-8")), apply):
        print(line)
    print("APPLIED" if apply else "DRY RUN — re-run with --apply to write")


if __name__ == "__main__":
    main()
