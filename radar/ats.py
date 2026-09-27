"""Connectors for the public job feeds behind most company career sites.

Each connector exposes:
  probe(session, slug, company, cfg) -> source dict or None   (used by discovery)
  from_url(url) -> source dict or None                         (parses a pasted careers URL)
  fetch(session, source, cfg) -> list of raw postings          (used by the daily run)

A raw posting is a dict: title, url, location, posted (datetime|None), description (text), id.
"""
import re
from urllib.parse import quote, urlparse

from .common import name_similar, parse_iso, parse_workday_posted, strip_html


def _get(s, url, cfg, **kw):
    r = s.get(url, timeout=cfg.get("request_timeout", 15), **kw)
    return r


# ---------------------------------------------------------------- Greenhouse
class Greenhouse:
    name = "greenhouse"

    @staticmethod
    def probe(s, slug, company, cfg):
        r = _get(s, f"https://boards-api.greenhouse.io/v1/boards/{slug}", cfg)
        if r.status_code != 200:
            return None
        board_name = (r.json() or {}).get("name", "")
        if company and board_name and not name_similar(board_name, company):  # company=None skips the check
            return None
        return {"ats": "greenhouse", "slug": slug, "board_name": board_name}

    @staticmethod
    def from_url(url):
        m = re.search(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)", url)
        return {"ats": "greenhouse", "slug": m.group(1)} if m else None

    @staticmethod
    def fetch(s, src, cfg):
        r = _get(s, f"https://boards-api.greenhouse.io/v1/boards/{src['slug']}/jobs?content=true", cfg)
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            out.append({
                "id": str(j.get("id")),
                "title": j.get("title", ""),
                "url": j.get("absolute_url", ""),
                "location": (j.get("location") or {}).get("name", ""),
                # first_published is the real post date; updated_at is a fallback that can look newer
                "posted": parse_iso(j.get("first_published") or j.get("updated_at")),
                "date_is_estimate": not j.get("first_published"),
                "description": strip_html(j.get("content", "")),
            })
        return out


# ---------------------------------------------------------------- Lever
class Lever:
    name = "lever"

    @staticmethod
    def probe(s, slug, company, cfg):
        r = _get(s, f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1", cfg)
        if r.status_code != 200 or not isinstance(r.json(), list) or not r.json():
            return None
        return {"ats": "lever", "slug": slug}

    @staticmethod
    def from_url(url):
        m = re.search(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)", url)
        return {"ats": "lever", "slug": m.group(1)} if m else None

    @staticmethod
    def fetch(s, src, cfg):
        r = _get(s, f"https://api.lever.co/v0/postings/{src['slug']}?mode=json", cfg)
        r.raise_for_status()
        out = []
        for j in r.json():
            cats = j.get("categories") or {}
            out.append({
                "id": j.get("id", ""),
                "title": j.get("text", ""),
                "url": j.get("hostedUrl", ""),
                "location": cats.get("location") or ", ".join(cats.get("allLocations") or []),
                "posted": parse_iso(j.get("createdAt")),
                "description": (j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or ""),
            })
        return out


# ---------------------------------------------------------------- Ashby
class Ashby:
    name = "ashby"

    @staticmethod
    def probe(s, slug, company, cfg):
        r = _get(s, f"https://api.ashbyhq.com/posting-api/job-board/{slug}", cfg)
        if r.status_code != 200 or not r.json().get("jobs"):
            return None
        return {"ats": "ashby", "slug": slug}

    @staticmethod
    def from_url(url):
        m = re.search(r"jobs\.ashbyhq\.com/([\w.-]+)", url)
        return {"ats": "ashby", "slug": m.group(1)} if m else None

    @staticmethod
    def fetch(s, src, cfg):
        r = _get(s, f"https://api.ashbyhq.com/posting-api/job-board/{src['slug']}", cfg)
        r.raise_for_status()
        out = []
        for j in r.json().get("jobs", []):
            if j.get("isListed") is False:
                continue
            loc = j.get("location") or ""
            if j.get("isRemote"):
                loc = f"{loc} (Remote)".strip()
            out.append({
                "id": j.get("id", ""),
                "title": j.get("title", ""),
                "url": j.get("jobUrl", ""),
                "location": loc,
                "posted": parse_iso(j.get("publishedAt")),
                "description": j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", "")),
            })
        return out


# ---------------------------------------------------------------- SmartRecruiters
class SmartRecruiters:
    name = "smartrecruiters"

    @staticmethod
    def probe(s, slug, company, cfg):
        r = _get(s, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", cfg)
        if r.status_code != 200 or not r.json().get("totalFound"):
            return None
        return {"ats": "smartrecruiters", "slug": slug}

    @staticmethod
    def from_url(url):
        m = re.search(r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)", url)
        return {"ats": "smartrecruiters", "slug": m.group(1)} if m else None

    @staticmethod
    def fetch(s, src, cfg):
        seen, out = set(), []
        for term in cfg["search_terms"]:
            url = f"https://api.smartrecruiters.com/v1/companies/{src['slug']}/postings?limit=100&q={quote(term)}"
            r = _get(s, url, cfg)
            r.raise_for_status()
            for j in r.json().get("content", []):
                if j["id"] in seen:
                    continue
                seen.add(j["id"])
                loc = j.get("location") or {}
                out.append({
                    "id": j["id"],
                    "title": j.get("name", ""),
                    "url": f"https://jobs.smartrecruiters.com/{src['slug']}/{j['id']}",
                    "location": ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country", "").upper()] if x)
                    + (" (Remote)" if loc.get("remote") else ""),
                    "posted": parse_iso(j.get("releasedDate")),
                    "description": "",  # fetched later only for matches
                    "_detail": f"https://api.smartrecruiters.com/v1/companies/{src['slug']}/postings/{j['id']}",
                })
        return out

    @staticmethod
    def detail(s, raw, cfg):
        r = _get(s, raw["_detail"], cfg)
        if r.status_code != 200:
            return ""
        secs = (r.json().get("jobAd") or {}).get("sections") or {}
        return strip_html(" ".join((v or {}).get("text", "") for v in secs.values()))


# ---------------------------------------------------------------- Workday
WD_URL = re.compile(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", re.I)


class Workday:
    name = "workday"
    PROBE_WD = ["wd1", "wd5", "wd3"]   # most common data centers; paste a URL for anything else
    PROBE_SITES = ["External", "Careers", "{t}", "External_Careers"]

    @staticmethod
    def _api(src):
        return f"https://{src['tenant']}.{src['wd']}.myworkdayjobs.com/wday/cxs/{src['tenant']}/{src['site']}"

    @staticmethod
    def _search(s, src, cfg, term, offset=0, limit=20):
        return s.post(Workday._api(src) + "/jobs", timeout=cfg.get("request_timeout", 15),
                      json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": term},
                      headers={"Content-Type": "application/json"})

    @staticmethod
    def verify(s, src, cfg):
        try:
            r = Workday._search(s, src, cfg, "", limit=1)
            return r.status_code == 200 and "jobPostings" in r.json()
        except Exception:
            return False

    @staticmethod
    def probe(s, slug, company, cfg):
        tenant = slug.replace("-", "")
        for wd in Workday.PROBE_WD:
            for site in Workday.PROBE_SITES:
                site = site.format(t=tenant)
                src = {"ats": "workday", "tenant": tenant, "wd": wd, "site": site}
                if Workday.verify(s, src, cfg):
                    return src
        return None

    @staticmethod
    def from_url(url):
        m = WD_URL.search(url)
        if not m:
            return None
        return {"ats": "workday", "tenant": m.group(1).lower(), "wd": m.group(2).lower(), "site": m.group(3)}

    @staticmethod
    def fetch(s, src, cfg):
        host = f"https://{src['tenant']}.{src['wd']}.myworkdayjobs.com"
        seen, out = set(), []
        for term in cfg["search_terms"]:
            for page in range(cfg.get("workday_max_pages", 5)):
                r = Workday._search(s, src, cfg, term, offset=page * 20)
                r.raise_for_status()
                posts = r.json().get("jobPostings") or []
                for j in posts:
                    path = j.get("externalPath", "")
                    if not path or path in seen:
                        continue
                    seen.add(path)
                    posted = parse_workday_posted(j.get("postedOn", ""))
                    out.append({
                        "id": (j.get("bulletFields") or [path])[0],
                        "title": j.get("title", ""),
                        "url": f"{host}/{src['site']}{path}",
                        "location": j.get("locationsText", ""),
                        "posted": posted,
                        "date_is_estimate": True,
                        "description": "",
                        "_detail": Workday._api(src) + path,
                    })
                if len(posts) < 20:  # results are relevance-sorted, so page until the cap
                    break
        return out

    @staticmethod
    def detail(s, raw, cfg):
        """Returns (description, exact_post_date|None, better_location)."""
        r = _get(s, raw["_detail"], cfg)
        if r.status_code != 200:
            return "", None, None
        info = r.json().get("jobPostingInfo") or {}
        loc = info.get("location")
        extra = info.get("additionalLocations") or []
        if extra:
            loc = "; ".join([loc] + extra) if loc else "; ".join(extra)
        return strip_html(info.get("jobDescription", "")), parse_iso(info.get("startDate")), loc


CONNECTORS = {c.name: c for c in (Greenhouse, Lever, Ashby, SmartRecruiters, Workday)}


def source_from_url(url):
    for c in CONNECTORS.values():
        src = c.from_url(url or "")
        if src:
            return src
    return None


def unsupported_host(url):
    host = urlparse(url or "").netloc.lower()
    for key, label in [("icims", "iCIMS"), ("taleo", "Oracle Taleo"), ("oraclecloud", "Oracle Cloud HCM"),
                       ("successfactors", "SAP SuccessFactors"), ("eightfold", "Eightfold"),
                       ("phenom", "Phenom"), ("jobvite", "Jobvite"), ("ultipro", "UKG")]:
        if key in host:
            return label
    return None
