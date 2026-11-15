"""Static checks on the website files, plus the browser-vs-Python statistics comparison."""
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["index.html", "browse.html", "trends.html", "explorer.html"]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def nav(html):
    """The whole navigation block (top bar and section tabs) with the current-page markers removed."""
    block = re.search(r"<!-- nav:start -->.*?<!-- nav:end -->", html, re.S).group(0)
    block = re.sub(r' aria-current="(page|true)"', "", block)
    return block.replace('class="link active"', 'class="link"')


REQUIRED = ["index.html", "browse.html", "trends.html"]


def test_three_required_pages_share_one_navigation_bar():
    """Assignment: all three pages share one navigation bar. Identical markup apart from which item is current."""
    navs = [nav(read(p)) for p in REQUIRED]
    assert navs[0] == navs[1] == navs[2]
    for page in REQUIRED:
        html = read(page)
        assert html.count('class="link active"') == 1 and '<a class="link active" href="index.html" aria-current="true">Markets</a>' in html
        assert f'<a href="{page}" aria-current="page">' in html                     # its own tab is the current page
    for target in REQUIRED:
        assert f'<a href="{target}"' in navs[0]                                      # Today, Browse and Trends are all reachable from every one of them


def test_navigation_is_organised_around_markets_research_and_portfolio():
    html = read("index.html")
    top = re.search(r'<div class="areas">(.*?)</div>', html, re.S).group(1)
    assert re.findall(r">([^<]+)</a>", top) == ["Markets", "Research", "Portfolio"]
    assert 'href="platform.html"' in html and ">About<" in html                       # About stays reachable but is not a major item
    for page, area in (("explorer.html", "Research"), ("fundamentals.html", "Research"), ("compare.html", "Research"), ("portfolio.html", "Portfolio")):
        assert re.search(r'<a class="link active" href="[^"]+" aria-current="(page|true)">%s</a>' % area, read(page)), page


def test_pages_share_fonts_colors_and_head():
    for p in PAGES:
        html = read(p)
        assert 'href="assets/css/site.css"' in html and 'rel="manifest" href="manifest.webmanifest"' in html
        assert "<title>CreditScope" in html and 'name="viewport"' in html and 'lang="en"' in html
        assert "assets/js/common.js" in html and "assets/js/stats.js" in html
    css = read("assets/css/site.css")
    assert "--font:" in css and ':root[data-theme="light"]' in css       # one font stack, dark default + light theme


def test_every_local_reference_exists():
    files = PAGES + ["assets/css/site.css", "assets/css/explorer.css"]
    for name in files:
        text = read(name)
        refs = re.findall(r'(?:href|src)="([^"#?]+)"', text) + re.findall(r"url\(['\"]?([^)'\"]+)", text)
        for ref in refs:
            if re.match(r"^(https?:|data:|mailto:)", ref):
                continue
            assert (ROOT / ref).exists(), f"{name} references missing file {ref}"


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_manifest_makes_the_site_installable():
    m = json.loads(read("manifest.webmanifest"))
    assert m["name"] and m["short_name"] and m["display"] in ("standalone", "fullscreen", "minimal-ui")
    assert (ROOT / m["start_url"].lstrip("./")).exists() and m["scope"] == "./"
    sizes = {}
    for icon in m["icons"]:
        assert (ROOT / icon["src"]).exists()
        if icon["src"].endswith(".png"):
            sizes[icon["sizes"]] = png_size(ROOT / icon["src"])
    assert sizes["192x192"] == (192, 192) and sizes["512x512"] == (512, 512)
    assert any(i["purpose"] == "maskable" for i in m["icons"])


def test_service_worker_precaches_real_files_and_handles_data_offline():
    sw = read("sw.js")
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    for path in re.findall(r"'([^']+)'", shell):
        assert path == "./" or (ROOT / path).exists(), f"sw.js precaches missing file {path}"
    for page in PAGES:
        assert page in shell
    assert "data/history.csv" in sw and "data/status.json" in sw
    assert "networkFirstData" in sw and "X-CS-Cache" in sw
    assert "serviceWorker" in read("assets/js/common.js")


def test_explorer_page_is_honest_about_simulated_data_and_return_types():
    html = read("explorer.html")
    assert 'id="synthBanner"' in html and "not real market prices" in html
    for needed in ("price return", "total return", "split-adjusted", "not adjusted for dividends"):
        assert needed in html.lower(), needed
    js = read("assets/js/explorer.js")
    assert "Finance.summarize" in js and "ExplorerSearch" in js and "basisLabel" in js


def test_pages_load_both_data_files_and_calculate_in_the_browser():
    common = read("assets/js/common.js")
    assert "data/history.csv" in common and "data/status.json" in common
    for p in ("today", "browse", "trends"):
        js = read(f"assets/js/{p}.js")
        assert "CS.load()" in js and "fetch(" not in js              # all data goes through the one loader


def approx_equal(a, b, path="expected"):
    """Deep comparison where floats may differ in the last digits (Python 3.12 sums floats more precisely)."""
    if isinstance(b, dict):
        assert isinstance(a, dict) and a.keys() == b.keys(), path
        for k in b:
            approx_equal(a[k], b[k], f"{path}.{k}")
    elif isinstance(b, list):
        assert isinstance(a, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            approx_equal(x, y, f"{path}[{i}]")
    elif isinstance(b, float) or isinstance(a, float):
        assert a == pytest.approx(b, rel=1e-12, abs=1e-12), path
    else:
        assert a == b, path


def test_fixtures_are_current():
    """tests/fixtures/sample is regenerated from the real pipeline + the Python reference."""
    sys.path.insert(0, str(ROOT / "tests"))
    import tempfile
    import make_fixtures
    with tempfile.TemporaryDirectory() as tmp:
        make_fixtures.build(Path(tmp))
        for name in ("history.csv", "status.json"):          # pipeline output is exactly reproducible
            assert (Path(tmp) / name).read_bytes() == (ROOT / "tests/fixtures/sample" / name).read_bytes(), name
        approx_equal(json.loads((Path(tmp) / "expected.json").read_text()),
                     json.loads((ROOT / "tests/fixtures/sample/expected.json").read_text()))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_statistics_match_independent_python_numbers():
    out = subprocess.run(["node", "--test", "tests/js/stats.test.js"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
