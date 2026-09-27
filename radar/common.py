import csv
import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def load_config():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    cfg["_roles"] = [(name, [re.compile(p, re.I) for p in pats]) for name, pats in cfg["roles"].items()]
    cfg["_exclude"] = [re.compile(p, re.I) for p in cfg.get("exclude_titles", [])]
    cfg["_nosponsor"] = [re.compile(p, re.I) for p in cfg.get("no_sponsorship_phrases", [])]
    cfg["_sponsor_ok"] = [re.compile(p, re.I) for p in cfg.get("sponsorship_ok_phrases", [])]
    cfg["_tz"] = ZoneInfo(cfg.get("timezone", "America/New_York"))
    return cfg


def load_companies():
    with open(ROOT / "companies.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["tier"] = int(r["tier"])
        r["rank"] = int(r["rank"])
    return rows


def session(workers=12):
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET", "POST"]))
    adapter = HTTPAdapter(max_retries=retry, pool_connections=workers, pool_maxsize=workers * 2)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (personal job-search radar; github actions)",
        "Accept": "application/json",
    })
    return s


# ---------- company-name -> ATS slug guesses ----------
SUFFIXES = r"\b(INC|INCORPORATED|LLC|LLP|LP|L P|PC|CORP|CORPORATION|CO|COMPANY|LIMITED|LTD|HOLDINGS?|GROUP|US|USA|NA|AMERICA|AMERICAS|THE|OF|AND|SERVICES|D/B/A.*|F/K/A.*)\b"
GENERIC_FIRST = {
    "american", "national", "united", "first", "global", "general", "international", "university",
    "state", "new", "north", "south", "east", "west", "digital", "data", "cloud", "tech", "info",
    "advanced", "capital", "premier", "smart", "systems", "software", "solutions", "technologies",
    "health", "medical", "children", "childrens", "st", "saint", "texas", "california", "boston",
    "bank", "city", "board", "trustees", "regents", "mount", "memorial", "baptist", "adventist",
}


def slug_candidates(name):
    """Return likely ATS board slugs for a company name, most specific first."""
    base = re.sub(r"\(.*?\)", " ", name.upper())
    base = base.replace("&", " AND ")
    core = re.sub(SUFFIXES, " ", base)
    words = [w.lower() for w in re.findall(r"[A-Z0-9]+", core)]
    if not words:
        return []
    out = ["".join(words), "-".join(words)]
    if len(words) >= 2:
        out.append("".join(words[:2]))
    first = words[0]
    if len(first) >= 5 and first not in GENERIC_FIRST:
        out.append(first)
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen and len(s) >= 3:
            seen.add(s)
            uniq.append(s)
    return uniq[:4]


def name_similar(a, b):
    """Loose check that an ATS board's display name belongs to the company."""
    def toks(x):
        x = re.sub(SUFFIXES, " ", x.upper().replace("&", " "))
        return {t for t in re.findall(r"[A-Z0-9]{3,}", x)}
    ta, tb = toks(a), toks(b)
    return bool(ta & tb)


# ---------- dates ----------
def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(value):
    if not value:
        return None
    if isinstance(value, (int, float)):  # epoch ms (Lever)
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    v = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d"):
        try:
            d = datetime.fromisoformat(v) if fmt is None else datetime.strptime(v[:10], fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


WD_POSTED = re.compile(r"posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)", re.I)


def parse_workday_posted(text, ref=None):
    """'Posted Today' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago' -> datetime (approx)."""
    ref = ref or now_utc()
    m = WD_POSTED.search(text or "")
    if not m:
        return None
    if m.group(1).lower() == "today":
        return ref
    if m.group(1).lower() == "yesterday":
        return ref - timedelta(days=1)
    days = int(m.group(2))
    if "+" in m.group(1):
        days += 1  # "30+ days" is older than 30
    return ref - timedelta(days=days)


# ---------- text ----------
TAG = re.compile(r"<[^>]+>")


def strip_html(s):
    if not s:
        return ""
    return re.sub(r"\s+", " ", TAG.sub(" ", html.unescape(html.unescape(s)))).strip()


US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
    "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR"
).split()
US_NAMES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|"
    "illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    "mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|"
    "north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|"
    "south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming|"
    "district of columbia|puerto rico"
)
US_RE = re.compile(
    r"\b(united states|usa|u\.s\.a?\.?|us-remote|remote[\s,-]*us|us[\s,-]*remote|" + US_NAMES + r")\b", re.I)
US_ABBR_RE = re.compile(  # case-sensitive so ", in" / ", or" don't count
    r",\s*(" + "|".join(US_STATES) + r")\b|^(" + "|".join(US_STATES) + r")\s*[-,]\s|\bUS\b")
NON_US_RE = re.compile(
    r"\b(canada|mexico|brazil|argentina|uk|united kingdom|england|ireland|germany|france|spain|italy|"
    r"netherlands|belgium|switzerland|basel|poland|india|china|japan|singapore|australia|israel|"
    r"philippines|costa rica)\b",
    re.I,
)


def looks_us(location):
    loc = location or ""
    if not loc.strip():
        return None  # unknown
    if US_RE.search(loc) or US_ABBR_RE.search(loc):
        return True
    if NON_US_RE.search(loc):
        return False
    return None
