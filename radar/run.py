"""Daily run: pull postings from every known feed, keep matching roles from the
last N days, and rebuild the dashboard.

    python -m radar.run              # run now
    python -m radar.run --scheduled  # used by GitHub Actions: only runs once per day, at/after 7 AM local
"""
import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from urllib.parse import quote_plus

from .ats import CONNECTORS
from .build import build_dashboard
from .common import DATA, DOCS, load_config, now_utc, session
from .match import is_recent, role_family, sponsorship_signal, us_flag


def source_key(src):
    if src["ats"] == "workday":
        return f"workday:{src['tenant']}:{src['site']}"
    return f"{src['ats']}:{src['slug'].lower()}"


def linkedin_search(company):
    q = f'"{company.title()}" ("project manager" OR "business analyst" OR consultant)'
    return f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(q)}&f_TPR=r604800&location=United%20States"


def fetch_source(s, key, src, companies, cfg):
    conn = CONNECTORS[src["ats"]]
    t0 = time.time()
    raw = conn.fetch(s, src, cfg)
    kept = []
    for r in raw:
        fam = role_family(r["title"], cfg)
        if not fam:
            continue
        # Workday "Posted N Days Ago" is approximate: allow an extra day until the detail call gives the exact date
        if not is_recent(r["posted"], cfg, slack_days=1 if r.get("date_is_estimate") else 0):
            continue
        desc, loc = r.get("description", ""), r.get("location", "")
        if src["ats"] == "workday":
            try:
                d, exact, better_loc = conn.detail(s, r, cfg)
                desc = d or desc
                loc = better_loc or loc
                if exact:
                    r["posted"], r["date_is_estimate"] = exact, False
            except Exception:
                pass
            if not is_recent(r["posted"], cfg):
                continue
        elif src["ats"] == "smartrecruiters":
            try:
                desc = conn.detail(s, r, cfg)
            except Exception:
                pass
        r.update(role=fam, description=desc, location=loc)
        kept.append(r)
    return key, src, companies, raw, kept, time.time() - t0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheduled", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config()
    tz = cfg["_tz"]
    local_now = now_utc().astimezone(tz)
    today = local_now.date().isoformat()
    last_run_file = DATA / "last_run.txt"
    if args.scheduled:
        if local_now.hour < cfg.get("run_hour", 7):
            print(f"It's {local_now:%H:%M} {tz.key}; waiting for the {cfg.get('run_hour', 7)}:00 slot.")
            return 0
        if last_run_file.exists() and last_run_file.read_text().strip() == today:
            print(f"Already ran today ({today}).")
            return 0

    src_file = DATA / "sources.json"
    if not src_file.exists():
        print("No data/sources.json yet. Run the 'Discover job feeds' workflow (or python -m radar.discover) first.")
        return 1
    entries = json.loads(src_file.read_text())
    tiers = set(cfg.get("tiers", [1, 2]))

    # Several H-1B entities can share one careers site (e.g. two CVS entities): fetch each feed once.
    feeds = {}
    for e in entries.values():
        if e["tier"] not in tiers or not e.get("source"):
            continue
        k = source_key(e["source"])
        feeds.setdefault(k, {"src": e["source"], "companies": []})["companies"].append(e)
    for f in feeds.values():
        f["companies"].sort(key=lambda c: c["rank"])

    seen_file = DATA / "seen.json"
    seen = json.loads(seen_file.read_text()) if seen_file.exists() else {}
    workers = cfg.get("max_workers", 12)
    s = session(workers)
    jobs, health = [], []
    t0 = time.time()
    with ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(fetch_source, s, k, f["src"], f["companies"], cfg): k for k, f in feeds.items()}
        for fut in as_completed(futs):
            k = futs[fut]
            comp = feeds[k]["companies"][0]
            try:
                key, src, companies, raw, kept, secs = fut.result()
            except Exception as ex:
                health.append({"company": comp["company"], "tier": comp["tier"], "ats": feeds[k]["src"]["ats"],
                               "ok": False, "error": str(ex)[:160]})
                continue
            health.append({"company": comp["company"], "tier": comp["tier"], "ats": src["ats"], "ok": True,
                           "postings": len(raw), "matches": len(kept)})
            for r in kept:
                jid = hashlib.sha1(f"{key}|{r.get('id') or r['url']}".encode()).hexdigest()[:12]
                first_seen = seen.setdefault(jid, today)
                posted_local = r["posted"].astimezone(tz)
                jobs.append({
                    "id": jid,
                    "company": comp["company"],
                    "also_files_as": [c["company"] for c in companies[1:]],
                    "tier": comp["tier"],
                    "sector": comp["sector"],
                    "h1b_rank": comp["rank"],
                    "h1b_filings": int(comp["h1b_filings"] or 0),
                    "h1b_avg_salary": int(comp["avg_salary"] or 0),
                    "title": r["title"].strip(),
                    "role": r["role"],
                    "url": r["url"],
                    "location": (r.get("location") or "").strip(),
                    "us": us_flag(r.get("location")),
                    "posted": posted_local.date().isoformat(),
                    "days_ago": max(0, (local_now.date() - posted_local.date()).days),
                    "date_estimate": bool(r.get("date_is_estimate")),
                    "first_seen": first_seen,
                    "sponsorship": sponsorship_signal(r.get("description", ""), cfg),
                    "board": src["ats"],
                })

    # forget ids we haven't seen for 45 days so seen.json doesn't grow forever
    cutoff = (local_now.date() - timedelta(days=45)).isoformat()
    live = {j["id"] for j in jobs}
    seen = {k: v for k, v in seen.items() if k in live or v >= cutoff}

    uncovered = [
        {"company": e["company"], "sector": e["sector"], "status": e["status"],
         "careers_url": e.get("careers_url", ""), "search_url": linkedin_search(e["company"]),
         "h1b_filings": int(e["h1b_filings"] or 0)}
        for e in entries.values() if e["tier"] == 1 and not e.get("source")
    ]
    jobs.sort(key=lambda j: (j["days_ago"], j["tier"], j["h1b_rank"]))
    meta = {
        "generated_at": local_now.isoformat(timespec="minutes"),
        "generated_label": local_now.strftime("%a %b %-d, %-I:%M %p ") + local_now.tzname(),
        "lookback_days": cfg.get("lookback_days", 7),
        "us_only_default": cfg.get("us_only_default", True),
        "roles": list(cfg["roles"].keys()),
        "feeds_checked": len(feeds),
        "feeds_failed": sum(1 for h in health if not h["ok"]),
        "tier1_companies": sum(1 for e in entries.values() if e["tier"] == 1),
        "tier1_covered": sum(1 for e in entries.values() if e["tier"] == 1 and e.get("source")),
        "runtime_s": round(time.time() - t0),
    }
    DATA.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    payload = {"meta": meta, "jobs": jobs, "uncovered": uncovered,
               "health": sorted(health, key=lambda h: (h["ok"], h["tier"], h["company"]))}
    (DOCS / "jobs.json").write_text(json.dumps(payload, indent=1))
    seen_file.write_text(json.dumps(seen))
    build_dashboard(payload)
    last_run_file.write_text(today)
    print(f"{len(jobs)} matching postings from {len(feeds)} feeds in {meta['runtime_s']}s "
          f"({meta['feeds_failed']} feeds failed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
