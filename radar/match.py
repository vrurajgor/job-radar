from datetime import timedelta

from .common import looks_us, now_utc


def role_family(title, cfg):
    """Return the configured role family for a title, or None."""
    t = title or ""
    if any(p.search(t) for p in cfg["_exclude"]):
        return None
    for name, pats in cfg["_roles"]:
        if any(p.search(t) for p in pats):
            return name
    return None


def is_recent(posted, cfg, ref=None, slack_days=0):
    if posted is None:
        return False
    ref = ref or now_utc()
    return posted >= ref - timedelta(days=cfg.get("lookback_days", 7) + slack_days, hours=12)


def sponsorship_signal(text, cfg):
    """'no' if the description suggests no visa sponsorship, 'yes' if it says it sponsors, else ''."""
    if not text:
        return ""
    if any(p.search(text) for p in cfg["_sponsor_ok"]):
        return "yes"
    if any(p.search(text) for p in cfg["_nosponsor"]):
        return "no"
    return ""


def us_flag(location):
    return looks_us(location)
