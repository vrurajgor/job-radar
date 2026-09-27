"""Offline end-to-end check with canned job-board responses (no network needed).

    python -m pytest tests/        or        python tests/test_offline.py
"""
import json
import shutil
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import radar.common as common  # noqa: E402

NOW = common.now_utc()
D = lambda n: (NOW - timedelta(days=n)).isoformat().replace("+00:00", "Z")  # noqa: E731


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


GH = {"jobs": [
    {"id": 1, "title": "Associate Project Manager, Clinical Operations", "absolute_url": "https://example.test/gh/1",
     "location": {"name": "Cambridge, MA"}, "first_published": D(1), "updated_at": D(0),
     "content": "&lt;p&gt;We are unable to sponsor visas for this role.&lt;/p&gt;"},
    {"id": 2, "title": "Director, Program Management", "absolute_url": "https://example.test/gh/2",
     "location": {"name": "Boston, MA"}, "first_published": D(1), "content": ""},
    {"id": 3, "title": "Business Analyst", "absolute_url": "https://example.test/gh/3",
     "location": {"name": "Basel, Switzerland"}, "first_published": D(2), "content": ""},
    {"id": 4, "title": "Project Manager", "absolute_url": "https://example.test/gh/4",
     "location": {"name": "Remote - US"}, "first_published": D(12), "content": ""},
]}
LEVER = [{"id": "a", "text": "Business Systems Analyst", "hostedUrl": "https://example.test/lever/a",
          "categories": {"location": "New York, NY"}, "createdAt": int((NOW - timedelta(days=3)).timestamp() * 1000),
          "descriptionPlain": "Visa sponsorship is available."}]
ASHBY = {"jobs": [{"id": "x", "title": "Healthcare Consultant", "jobUrl": "https://example.test/ashby/x",
                   "location": "Chicago, IL", "publishedAt": D(0), "descriptionPlain": "", "isListed": True}]}
SR_LIST = {"totalFound": 1, "content": [{"id": "99", "name": "Senior Consultant", "releasedDate": D(5),
                                         "location": {"city": "Austin", "region": "TX", "country": "us"}}]}
SR_DETAIL = {"jobAd": {"sections": {"jobDescription": {"text": "Must be a U.S. citizen."}}}}
WD_LIST = {"total": 2, "jobPostings": [
    {"title": "Project Manager, Protein Therapies", "externalPath": "/job/Tarrytown-NY/PM_R1",
     "locationsText": "Tarrytown, NY", "postedOn": "Posted 2 Days Ago", "bulletFields": ["R1"]},
    {"title": "Program Manager", "externalPath": "/job/Old/PM_R2", "locationsText": "Rensselaer, NY",
     "postedOn": "Posted 30+ Days Ago", "bulletFields": ["R2"]}]}
WD_DETAIL = {"jobPostingInfo": {"jobDescription": "<p>Great role</p>", "startDate": (NOW - timedelta(days=2)).date().isoformat(),
                                "location": "Tarrytown, NY"}}


class FakeSession:
    headers = {}

    def get(self, url, **kw):
        if "greenhouse" in url: return Resp(GH)
        if "lever" in url: return Resp(LEVER)
        if "ashbyhq" in url: return Resp(ASHBY)
        if "smartrecruiters" in url: return Resp(SR_DETAIL if url.rstrip("/").endswith("/99") else SR_LIST)
        if "myworkdayjobs" in url: return Resp(WD_DETAIL)
        return Resp({}, 404)

    def post(self, url, json=None, **kw):
        if "myworkdayjobs" in url:
            return Resp(WD_LIST if (json or {}).get("offset", 0) == 0 else {"jobPostings": []})
        return Resp({}, 404)


def run(tmp):
    common.DATA = tmp / "data"; common.DOCS = tmp / "docs"
    import radar.build as build, radar.run as run_mod
    build.DOCS = common.DOCS; run_mod.DATA = common.DATA; run_mod.DOCS = common.DOCS
    run_mod.session = lambda *a, **k: FakeSession()
    common.DATA.mkdir(parents=True)
    base = {"h1b_filings": "500", "avg_salary": "120000"}
    sources = {
        "ACME BIO INC": dict(base, rank=10, company="ACME BIO INC", tier=1, sector="Pharma & Biotech", status="x", source={"ats": "greenhouse", "slug": "acmebio"}),
        "LEV HEALTH INC": dict(base, rank=20, company="LEV HEALTH INC", tier=1, sector="Health tech & Health IT", status="x", source={"ats": "lever", "slug": "levhealth"}),
        "ASH CONSULTING LLC": dict(base, rank=30, company="ASH CONSULTING LLC", tier=2, sector="Other", status="x", source={"ats": "ashby", "slug": "ash"}),
        "SMART CO": dict(base, rank=40, company="SMART CO", tier=2, sector="Other", status="x", source={"ats": "smartrecruiters", "slug": "smart"}),
        "REGEN PHARMA INC": dict(base, rank=5, company="REGEN PHARMA INC", tier=1, sector="Pharma & Biotech", status="x", source={"ats": "workday", "tenant": "regen", "wd": "wd1", "site": "Careers"}),
        "NOFEED HOSPITAL": dict(base, rank=50, company="NOFEED HOSPITAL", tier=1, sector="Hospitals & Health systems", status="not found", source=None),
    }
    (common.DATA / "sources.json").write_text(json.dumps(sources))
    assert run_mod.main([]) == 0
    return json.loads((common.DOCS / "jobs.json").read_text())


def test_end_to_end():
    tmp = Path(tempfile.mkdtemp())
    try:
        out = run(tmp)
        titles = {j["title"]: j for j in out["jobs"]}
        assert "Director, Program Management" not in titles          # excluded seniority
        assert "Project Manager" not in titles                       # 12 days old
        assert "Program Manager" not in titles                       # Workday 30+ days
        assert titles["Associate Project Manager, Clinical Operations"]["sponsorship"] == "no"
        assert titles["Associate Project Manager, Clinical Operations"]["role"] == "Associate Project Manager"
        assert titles["Business Analyst"]["us"] is False
        assert titles["Business Systems Analyst"]["sponsorship"] == "yes"
        assert titles["Senior Consultant"]["sponsorship"] == "no"
        wd = titles["Project Manager, Protein Therapies"]
        assert wd["date_estimate"] is False and wd["url"].endswith("/Careers/job/Tarrytown-NY/PM_R1")
        assert [u["company"] for u in out["uncovered"]] == ["NOFEED HOSPITAL"]
        html = (tmp / "docs" / "index.html").read_text()
        assert "/*__DATA__*/null" not in html and "Protein Therapies" in html
        print(f"OK: {len(out['jobs'])} jobs -> {sorted(titles)}")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    test_end_to_end()
