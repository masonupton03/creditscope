"""Structural quality of every HTML page: accessibility basics, navigation, links and assets that must exist."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted(p.name for p in ROOT.glob("*.html"))
RESEARCH = ["explorer.html", "fundamentals.html", "compare.html", "portfolio.html", "platform.html"]


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.ids, self.labels_for, self.links, self.assets, self.title, self._in_title = [], [], set(), [], [], "", False
        self.buttons, self.inputs, self.canvases, self.imgs, self.h1 = [], [], [], [], 0
        self._btn = None
        self._label_depth = 0
        self.lang = self.viewport = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = a.get("content")
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self.h1 += 1
        if tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.labels_for.add(a["for"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("script", "img") and a.get("src"):
            self.assets.append(a["src"])
        if tag == "link" and a.get("href"):
            self.assets.append(a["href"])
        if tag == "button":
            self._btn = {"label": a.get("aria-label") or a.get("title"), "text": "", "id": a.get("id")}
        wrapped = self._label_depth > 0
        if tag == "input" and a.get("type") not in ("hidden", "submit"):
            self.inputs.append(dict(a, _wrapped=wrapped))
        if tag == "select":
            self.inputs.append(dict(a, _wrapped=wrapped))
        if tag == "canvas":
            self.canvases.append(a)
        if tag == "img":
            self.imgs.append(a)

    def handle_endtag(self, tag):
        if tag == "label":
            self._label_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "button" and self._btn is not None:
            self.buttons.append(self._btn)
            self._btn = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._btn is not None:
            self._btn["text"] += data


def parse(name):
    p = Page()
    p.feed((ROOT / name).read_text(encoding="utf-8"))
    return p


@pytest.fixture(scope="module")
def pages():
    return {n: parse(n) for n in PAGES}


def test_every_page_has_the_basics(pages):
    titles = []
    for n, p in pages.items():
        assert p.lang == "en", n
        assert p.viewport and "width=device-width" in p.viewport, n
        assert p.title.strip().startswith("CreditScope"), n
        titles.append(p.title.strip())
        assert p.h1 == 1, f"{n}: exactly one h1"
        assert "main" in p.tags, f"{n}: a main landmark"
        assert "nav" in p.tags and "footer" in p.tags, n
        assert len(p.ids) == len(set(p.ids)), f"{n}: duplicate ids {[i for i in p.ids if p.ids.count(i) > 1]}"
    assert len(titles) == len(set(titles)), "page titles must be unique"


def test_research_pages_have_a_skip_link_that_lands_somewhere_and_a_subnav(pages):
    for n in RESEARCH:
        text = (ROOT / n).read_text(encoding="utf-8")
        m = re.search(r'<a class="skip" href="#([\w-]+)"', text)
        assert m and m.group(1) in pages[n].ids, f"{n}: skip link target must exist"
        assert 'aria-label="Research tools"' in text
        assert len(re.findall(r'<a href="[\w.]+\.html" aria-current="page"', re.search(r'<nav class="subnav".*?</nav>', text, re.S).group(0))) == 1, n
        assert re.search(r'<a href="%s" aria-current="page"' % n, text), f"{n}: its own sub-navigation link is current"


def test_required_pages_get_a_skip_link_but_not_the_research_navigation(pages):
    for n in ("index.html", "browse.html", "trends.html"):
        text = (ROOT / n).read_text(encoding="utf-8")
        assert "subnav" not in text and 'class="skip" href="#main"' in text and "main" in pages[n].ids, n


def test_all_controls_have_accessible_names(pages):
    for n, p in pages.items():
        for b in p._btn and [] or p.buttons:
            assert (b["label"] or b["text"].strip()) or b["id"] in ("installBtn", "divBtn"), f"{n}: unnamed button {b}"
        for i in p.inputs:
            named = i.get("aria-label") or i.get("id") in p.labels_for or i.get("_wrapped") or i.get("title")
            assert named, f"{n}: unlabelled control {i}"
        for c in p.canvases:
            assert c.get("role") == "img" and c.get("aria-label"), f"{n}: canvas needs role=img and aria-label"
        for img in p.imgs:
            assert "alt" in img, f"{n}: img needs alt"


def test_local_links_and_assets_exist(pages):
    for n, p in pages.items():
        for ref in p.links + p.assets:
            if re.match(r"^(https?:|mailto:|#|data:)", ref):
                continue
            path = ref.split("#")[0].split("?")[0]
            assert (ROOT / path).exists(), f"{n}: broken reference {ref}"
        for a in p.links:
            if a.startswith("#"):
                assert a[1:] in p.ids or a == "#", f"{n}: dangling anchor {a}"


def test_external_links_in_pages_open_safely():
    for n in PAGES:
        for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", (ROOT / n).read_text(encoding="utf-8")):
            assert 'rel="noopener' in tag, f"{n}: {tag}"


def test_service_worker_precaches_every_page_and_script_the_pages_use(pages):
    sw = (ROOT / "sw.js").read_text()
    shell = sw.split("const SHELL")[1].split("];")[0]
    for n, p in pages.items():
        assert f"'{n}'" in shell, f"{n} missing from the offline shell"
        for a in p.assets:
            if a.startswith(("assets/", "explorer/")):
                assert f"'{a}'" in shell, f"{a} (used by {n}) missing from the offline shell"
    assert "creditscope-v6" in sw
