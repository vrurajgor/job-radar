import json

from .common import DOCS, ROOT

TEMPLATE = ROOT / "dashboard" / "template.html"


def build_dashboard(payload, out=None):
    """Embed the data into the dashboard template -> docs/index.html (served by GitHub Pages)."""
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", data)
    out = out or DOCS / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    (DOCS / ".nojekyll").write_text("")
    return out


if __name__ == "__main__":  # rebuild the page from the last docs/jobs.json without refetching
    build_dashboard(json.loads((DOCS / "jobs.json").read_text()))
    print("Rebuilt docs/index.html")
