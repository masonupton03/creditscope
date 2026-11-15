"""Polite client for SEC EDGAR's public JSON.

The SEC asks every automated client to identify itself in the User-Agent header with contact details and to stay below
10 requests per second. The contact is NOT stored in the repository: it is read from the SEC_USER_AGENT environment variable
(a GitHub Actions secret in CI). It is never printed, logged, written to output files or included in error messages.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request

ENV = "SEC_USER_AGENT"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{taxonomy}/{tag}.json"
MIN_INTERVAL = 0.2                                              # at most 5 requests per second (the SEC's limit is 10)


class SecError(Exception):
    """Messages never contain the User-Agent."""


def user_agent_from_env(env=None) -> str:
    value = (env if env is not None else os.environ).get(ENV, "").strip()
    if not value:
        raise SecError(f"{ENV} is not set. Set it to 'ProjectName contact-address' (a dedicated project mailbox) before contacting the SEC.")
    if not re.search(r"\S+@\S+\.\S+", value) or len(value) > 200 or re.search(r"[\[\]<>{}]|YOUR|PLACEHOLDER|example\.(com|org)", value, re.I):
        raise SecError(f"{ENV} must contain a real contact address (and no placeholders). Value not shown.")
    return value


class SecClient:
    def __init__(self, user_agent: str, tickers_url: str = TICKERS_URL, facts_url: str = FACTS_URL, concept_url: str = CONCEPT_URL, sleep=time.sleep,
                 min_interval: float = MIN_INTERVAL, retries: int = 3):
        self._ua = user_agent
        self.tickers_url, self.facts_url, self.concept_url = tickers_url, facts_url, concept_url
        self._sleep, self._interval, self._retries = sleep, min_interval, retries
        self._last = 0.0
        self.requests = 0

    def __repr__(self):
        return "SecClient(user_agent=<hidden>)"

    def _get(self, url: str):
        wait = self._interval - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        for attempt in range(self._retries + 1):
            self._last = time.monotonic()
            self.requests += 1
            req = urllib.request.Request(url, headers={"User-Agent": self._ua, "Accept-Encoding": "gzip"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    return json.loads(raw)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (429, 500, 502, 503, 504) and attempt < self._retries:
                    self._sleep(2 ** attempt * 2)
                    continue
                raise SecError(f"SEC returned HTTP {e.code} for {url.split('?')[0]}") from None
            except (urllib.error.URLError, TimeoutError, ValueError):
                if attempt < self._retries:
                    self._sleep(2 ** attempt)
                    continue
                raise SecError(f"could not read {url.split('?')[0]}") from None
        raise SecError("unreachable")

    def tickers(self) -> dict:
        """{TICKER: {'cik': int, 'name': str}} from the SEC's ticker file (the SEC does not guarantee its accuracy)."""
        raw = self._get(self.tickers_url) or {}
        out = {}
        for row in (raw.values() if isinstance(raw, dict) else raw):
            try:
                out.setdefault(str(row["ticker"]).upper(), {"cik": int(row["cik_str"]), "name": str(row["title"])})
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def company_facts(self, cik: int):
        return self._get(self.facts_url.format(cik=cik))

    def company_concept(self, cik: int, tag: str, taxonomy: str = "us-gaap"):
        """One concept for one company from a different SEC endpoint than company_facts (used to cross-check the build)."""
        return self._get(self.concept_url.format(cik=cik, taxonomy=taxonomy, tag=tag))
