"""Find the public job feed for each company in companies.csv.

Run weekly (the GitHub workflow does this on Sundays) or by hand:
    python -m radar.discover            # all tiers in config.yaml
    python -m radar.discover --tier 1   # healthcare only (faster)

Writes data/sources.json. Companies with no feed found keep their row, so the
dashboard can offer a manual search link for them.
"""
import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ats import CONNECTORS, Workday, source_from_url, unsupported_host
from .common import DATA, ROOT, load_companies, load_config, session, slug_candidates


def load_manual():
    path = ROOT / "sources_manual.csv"
    if not path.exists():
        return {}
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("company") or "").strip() and not r["company"].startswith("#")]
    return {r["company"].strip().upper(): r for r in rows}


def verify(s, src, company, cfg):
    try:
        if src["ats"] == "workday":
            return Workday.verify(s, src, cfg)
        return CONNECTORS[src["ats"]].probe(s, src["slug"], company, cfg) is not None
    except Exception:
        return False


def verify_pasted(s, src, cfg):
    """A URL the user pasted is trusted as the right company; only check the feed responds."""
    try:
        if src["ats"] == "workday":
            return Workday.verify(s, src, cfg)
        return CONNECTORS[src["ats"]].probe(s, src["slug"], None, cfg) is not None
    except Exception:
        return False


def auto_probe(s, company, tier, cfg):
    slugs = slug_candidates(company)
    for slug in slugs:  # Greenhouse returns a board name, so every guess can be checked
        try:
            hit = CONNECTORS["greenhouse"].probe(s, slug, company, cfg)
            if hit:
                return hit
        except Exception:
            pass
    for ats in ("lever", "ashby", "smartrecruiters"):  # no name check possible: full-name slugs only
        for slug in slugs[:2]:
            try:
                hit = CONNECTORS[ats].probe(s, slug, company, cfg)
                if hit:
                    return hit
            except Exception:
                pass
    if tier == 1:  # Workday needs tenant + data center + site name, so only guess for healthcare companies
        tenants = [x for x in slugs if "-" not in x]
        for t in (tenants[:1] + tenants[-1:]) if len(tenants) > 1 else tenants:
            try:
                hit = Workday.probe(s, t, company, cfg)
                if hit:
                    return hit
            except Exception:
                pass
    return None


def discover_one(s, row, manual, previous, cfg):
    name = row["company"]
    entry = {k: row[k] for k in ("rank", "company", "tier", "sector", "h1b_filings", "avg_salary")}
    entry.update(source=None, status="not found", careers_url="")
    m = manual.get(name.upper())
    if m:
        action = (m.get("action") or "use").strip().lower()
        url = (m.get("careers_url") or "").strip()
        entry["careers_url"] = url
        if action == "skip":
            entry["status"] = "skipped by you"
            return entry
        src = source_from_url(url)
        if src:
            if verify_pasted(s, src, cfg):
                entry.update(source=src, status="from your list")
                return entry
            hit = auto_probe(s, name, row["tier"], cfg)  # the pasted URL may be stale; try guessing
            if hit:
                entry.update(source=hit, status="found automatically (your URL didn't respond)")
            else:
                entry["status"] = "your URL didn't respond - check it in sources_manual.csv"
            return entry
        label = unsupported_host(url)
        if label:
            entry["status"] = f"{label} site - search manually"
            return entry
        if url:
            entry["status"] = "custom careers site - search manually"
            return entry
    prev = (previous.get(name) or {}).get("source")
    if prev and verify(s, prev, name, cfg):
        entry.update(source=prev, status="found automatically")
        return entry
    hit = auto_probe(s, name, row["tier"], cfg)
    if hit:
        entry.update(source=hit, status="found automatically")
    return entry


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, action="append", help="limit to tier(s); default = config tiers")
    ap.add_argument("--limit", type=int, help="only the first N companies (for testing)")
    args = ap.parse_args(argv)
    cfg = load_config()
    tiers = args.tier or cfg.get("tiers", [1, 2])
    companies = [c for c in load_companies() if c["tier"] in tiers]
    if args.limit:
        companies = companies[: args.limit]
    manual = load_manual()
    out_path = DATA / "sources.json"
    previous = json.loads(out_path.read_text()) if out_path.exists() else {}
    workers = cfg.get("max_workers", 12)
    s = session(workers)
    t0 = time.time()
    results = dict(previous)  # keep tiers we didn't re-scan this time
    with ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(discover_one, s, row, manual, previous, cfg): row for row in companies}
        for i, f in enumerate(as_completed(futs), 1):
            e = f.result()
            results[e["company"]] = e
            if i % 100 == 0:
                print(f"  {i}/{len(companies)} checked ({time.time() - t0:.0f}s)", flush=True)
    DATA.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(dict(sorted(results.items(), key=lambda kv: kv[1]["rank"])), indent=1))
    found = [e for e in results.values() if e["source"]]
    t1 = [e for e in results.values() if e["tier"] == 1]
    print(f"Done in {time.time() - t0:.0f}s. Feeds found for {len(found)}/{len(results)} companies "
          f"({sum(1 for e in t1 if e['source'])}/{len(t1)} in Tier 1).")
    by_ats = {}
    for e in found:
        by_ats[e["source"]["ats"]] = by_ats.get(e["source"]["ats"], 0) + 1
    print("By job board:", by_ats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
