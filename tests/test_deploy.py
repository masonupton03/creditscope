"""The GitHub Pages artifact: .github/workflows/pages.yml's staging step is executed on a copy of the tracked files, and the result is checked.

A page, asset or data file that the site needs but the workflow forgets to copy fails here, before a merge, instead of as a 404 on the live site.
"""
from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["index.html", "browse.html", "trends.html", "explorer.html", "fundamentals.html", "compare.html", "portfolio.html", "platform.html"]
REQUIRED = ["index.html", "browse.html", "trends.html"]
LOCAL = re.compile(r"^(?!https?:|mailto:|data:|javascript:|#|//)")


def staging_script() -> str:
    text = (ROOT / ".github" / "workflows" / "pages.yml").read_text()
    m = re.search(r"- name: Stage the site[^\n]*\n\s+run: \|\n((?:          [^\n]*\n)+)", text)
    assert m, "the staging step was not found in pages.yml"
    return "".join(line[10:] + "\n" for line in m.group(1).splitlines())


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    work = tmp_path_factory.mktemp("deploy")
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    for rel in tracked:
        src = ROOT / rel
        if src.is_file():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, work / rel)
    subprocess.run(["bash", "-e", "-c", staging_script()], cwd=work, check=True)
    return work / "_site"


def files(site: Path) -> set:
    return {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}


def local_refs(html: str) -> set:
    return {m.split("#")[0].split("?")[0] for m in re.findall(r'(?:href|src)="([^"]+)"', html) if LOCAL.match(m)} - {""}


def test_every_page_loads_every_local_link_script_stylesheet_and_image_it_references(site):
    present, missing = files(site), []
    for page in PAGES:
        assert page in present, f"{page} is not in the artifact"
        for ref in local_refs((site / page).read_text()):
            if ref not in present and not (ref.endswith("/") and any(f.startswith(ref) for f in present)):
                missing.append((page, ref))
    assert not missing, missing


def test_navigation_destinations_all_exist_and_together_reach_every_page(site):
    reached = set()
    for page in PAGES:
        html = (site / page).read_text()
        nav = re.search(r"<!-- nav:start -->(.*?)<!-- nav:end -->", html, re.S)
        assert nav, page
        hrefs = re.findall(r'href="([^"]+)"', nav.group(1))
        reached |= {h.split('#')[0] for h in hrefs if LOCAL.match(h)}
        for h in hrefs:
            if LOCAL.match(h):
                assert h.split("#")[0] in files(site), (page, h)
    assert set(PAGES) <= reached, set(PAGES) - reached


def test_service_worker_shell_manifest_and_icons_are_all_in_the_artifact(site):
    present = files(site)
    sw = (site / "sw.js").read_text()
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    entries = re.findall(r"'([^']+)'", shell)
    assert len(entries) > 30
    assert [e for e in entries if e != "./" and e not in present] == []
    man = json.loads((site / "manifest.webmanifest").read_text())
    assert man["start_url"] and all(i["src"] in present for i in man["icons"])
    css = "".join((site / c).read_text() for c in present if c.endswith(".css"))
    assert [u for u in re.findall(r"url\(['\"]?([^)'\"]+)", css) if LOCAL.match(u) and u not in present] == []


def test_only_the_approved_sec_companies_are_published(site):
    cur = json.loads((ROOT / "fundamentals" / "curated.json").read_text())["release"]
    assert cur == ["AAPL", "MSFT"]
    sec = sorted(p.stem for p in (site / "explorer" / "sec" / "company").glob("*.json"))
    assert sec == sorted(cur)
    index = json.loads((site / "explorer" / "sec" / "index.json").read_text())
    assert [e["s"] for e in index["entries"]] == ["AAPL", "MSFT"] and index["meta"]["synthetic"] is False
    blob = "".join((site / f).read_text() for f in files(site) if f.startswith("explorer/sec/"))
    assert "WMT" not in blob and "JPM" not in blob and "Walmart" not in blob and "JPMORGAN" not in blob.upper()
    for t in cur:                                                          # every public company carries its limitations and what was verified
        c = json.loads((site / "explorer" / "sec" / "company" / f"{t}.json").read_text())
        assert c["verification"]["unverified"] and len(c["limitations"]) >= 2 and c["coverage"]["balanceSheetBasis"]


def test_the_three_assignment_pages_and_their_data_are_unchanged_in_the_artifact(site):
    for page in REQUIRED:
        assert (site / page).read_text() == (ROOT / page).read_text()
    assert (site / "data" / "history.csv").read_bytes() == (ROOT / "data" / "history.csv").read_bytes()
    assert (site / "data" / "status.json").read_bytes() == (ROOT / "data" / "status.json").read_bytes()
    assert sorted(p.name for p in (site / "data").iterdir()) == ["history.csv", "status.json"]       # no raw responses, no run logs
    for js in ("common.js", "stats.js", "today.js", "browse.js", "trends.js"):
        assert (site / "assets" / "js" / js).exists()
    sw = (site / "sw.js").read_text()
    assert "'data/history.csv', 'data/status.json'" in sw


def test_nothing_private_or_unrelated_is_in_the_artifact(site):
    bad = ["*.env", ".env*", "credentials*", "*.pem", "*.key", "private*", ".creditscope*", "*.bak", "*.py", "*.gz", "tests/*", "docs/*", "personal/*", "scripts/*", "creditscope/*", "fundamentals/*", "data/raw/*", "data/runs/*"]
    leaked = [f for f in files(site) if any(fnmatch.fnmatch(f, p) or fnmatch.fnmatch(Path(f).name, p) for p in bad)]
    assert not leaked, leaked
    portfolios = [f for f in files(site) if re.search(r"portfolio.*\.json$", f)]
    assert portfolios == ["explorer/sample/portfolio.json"]                  # only the invented demonstration portfolio
    assert {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"} <= files(site)
    top = {f for f in files(site) if "/" not in f}
    assert top == set(PAGES) | {"manifest.webmanifest", "sw.js", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", ".nojekyll"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_service_worker_never_caches_private_personal_edition_paths():
    script = r"""
const fs = require('fs'), vm = require('vm');
const listeners = {};
const cache = { put: () => { cache.puts = (cache.puts || 0) + 1; }, match: async () => undefined, add: async () => {}, addAll: async () => {} };
const ctx = { self: null, caches: { open: async () => cache, keys: async () => [], delete: async () => true }, URL, Response, Headers,
  fetch: async () => new Response('x', { status: 200 }), console };
ctx.self = Object.assign(ctx, { location: new URL('https://example.test/creditscope/sw.js'), registration: { scope: 'https://example.test/creditscope/' }, clients: { claim: async () => {} }, skipWaiting: async () => {},
  addEventListener: (t, f) => { listeners[t] = f; } });
vm.createContext(ctx); vm.runInContext(fs.readFileSync('sw.js', 'utf8'), ctx);
const out = {};
for (const p of ['api/portfolio', 'api/series/AAPL', 'private-data/ledger.json', 'explorer/sample/index.json', 'data/history.csv']) {
  let handled = false;
  listeners.fetch({ request: { method: 'GET', url: 'https://example.test/creditscope/' + p, mode: 'cors' }, respondWith: () => { handled = true; } });
  out[p] = handled;
}
let put = false;
listeners.fetch({ request: { method: 'PUT', url: 'https://example.test/creditscope/api/portfolio', mode: 'cors' }, respondWith: () => { put = true; } });
out.PUT = put;
console.log(JSON.stringify(out));
"""
    res = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    seen = json.loads(res.stdout.strip().splitlines()[-1])
    assert seen["api/portfolio"] is False and seen["api/series/AAPL"] is False and seen["private-data/ledger.json"] is False and seen["PUT"] is False
    assert seen["explorer/sample/index.json"] is True and seen["data/history.csv"] is True            # the public files are cached as designed
