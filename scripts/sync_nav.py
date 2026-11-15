"""Single source of truth for the site navigation. Every page carries the same top bar (Markets, Research, Portfolio, About, theme) and,
for Markets and Research, a row of section tabs. The markup is generated here so the pages cannot drift apart.

    python3 scripts/sync_nav.py            # rewrite the navigation in every page
    python3 scripts/sync_nav.py --check    # exit 1 if any page differs from the template (tests/test_pages.py runs the same check)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AREAS = [("markets", "Markets", "index.html"), ("research", "Research", "explorer.html"), ("portfolio", "Portfolio", "portfolio.html")]
SUB = {
    "markets": [("Today", "index.html"), ("Browse", "browse.html"), ("Trends", "trends.html")],
    "research": [("Explorer", "explorer.html"), ("Fundamentals", "fundamentals.html"), ("Compare", "compare.html")],
}
PAGES = {"index.html": "markets", "browse.html": "markets", "trends.html": "markets", "explorer.html": "research", "fundamentals.html": "research",
         "compare.html": "research", "portfolio.html": "portfolio", "platform.html": None}
MARK = ('<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1.5" y="1.5" width="21" height="21" rx="6" fill="none" stroke="currentColor" stroke-opacity=".4" stroke-width="1.5"/>'
        '<polyline points="6,15.5 10,11.5 13.5,14 18,8" fill="none" stroke="#3987e5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
START, END = "<!-- nav:start -->", "<!-- nav:end -->"


def render(page: str) -> str:
    area = PAGES[page]
    links = []
    for key, label, href in AREAS:
        if key == area:
            cur = ' aria-current="page"' if key not in SUB else ' aria-current="true"'     # "page" only where the area has no tab row of its own
            links.append(f'<a class="link active" href="{href}"{cur}>{label}</a>')
        else:
            links.append(f'<a class="link" href="{href}">{label}</a>')
    about_cur = ' aria-current="page"' if page == "platform.html" else ""
    out = [START,
           '<nav class="nav" aria-label="Main"><div class="wrap">',
           f'<a class="brand" href="index.html" aria-label="CreditScope home">{MARK}<span class="word">CreditScope</span></a>',
           '<div class="areas">' + "".join(links) + "</div>",
           '<span class="spacer"></span>',
           f'<a class="util" href="platform.html"{about_cur}>About</a>',
           '<button class="btn small label" id="installBtn" type="button" hidden>Install app</button>',
           '<button class="btn icon" id="themeBtn" type="button" aria-label="Switch to light theme" title="Toggle light / dark theme">☀</button>',
           "</div></nav>"]
    if area in SUB:
        tabs = "".join(f'<a href="{href}"' + (' aria-current="page"' if href == page else "") + f">{label}</a>" for label, href in SUB[area])
        out.append(f'<nav class="subnav" aria-label="{dict((k, l) for k, l, _ in AREAS)[area]} pages"><div class="wrap">{tabs}</div></nav>')
    out.append(END)
    return "\n".join(out)


def apply(text: str, page: str) -> str:
    block = render(page)
    if START in text:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: block, text, count=1, flags=re.S)
    return re.sub(r'<nav class="nav[^"]*"[^>]*>.*?</nav>\s*(?:<nav class="subnav"[^>]*>.*?</nav>)?', lambda m: block, text, count=1, flags=re.S)


def main(argv):
    check = "--check" in argv
    bad = []
    for page in PAGES:
        p = ROOT / page
        old = p.read_text(encoding="utf-8")
        new = apply(old, page)
        if new != old:
            bad.append(page)
            if not check:
                p.write_text(new, encoding="utf-8")
    if check:
        print("navigation differs from the template in: " + ", ".join(bad) if bad else "navigation is in sync")
        return 1 if bad else 0
    print("updated: " + ", ".join(bad) if bad else "already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
