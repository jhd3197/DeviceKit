"""Per-engine search adapters — the one place engine-specific knowledge lives.

Each adapter is ``{build_url, parse}``: how to turn a query into a results URL, and how to pull
``{title, url, snippet}`` out of the returned HTML. Keeping this per-engine means a Google DOM
drift is a one-function fix, and the *resilience contract* is explicit:

* ``parse`` returns a (possibly empty) list of results when it recognises the results region.
* ``parse`` raises :class:`ParseError` when the results **container is absent** — DOM drift, a
  consent wall, or an anti-bot page. The caller turns that into an explicit "couldn't parse"
  error rather than an empty list that masquerades as "no results" (plan 17).

Parsing uses ``beautifulsoup4`` (a core backend dependency, so no extension ``requirements.txt``
/ pip gate). DuckDuckGo uses the server-rendered ``html.duckduckgo.com`` endpoint, which needs no
JavaScript — ideal for driving through a device's Chrome.
"""
import re
import urllib.parse

from bs4 import BeautifulSoup

SUPPORTED = ("google", "bing", "duckduckgo")


class ParseError(Exception):
    """The results container wasn't found — the page structure changed or the request was
    blocked. Distinct from an empty-but-valid results page."""


def _soup(html):
    return BeautifulSoup(html or "", "html.parser")


def _abs_text(node, limit=400):
    return node.get_text(" ", strip=True)[:limit] if node else ""


# --------------------------------------------------------------------------- Google
_GOOGLE_BAD = (
    "google.com/search", "google.com/preferences", "google.com/setprefs",
    "accounts.google.", "support.google.", "policies.google.", "maps.google.",
    "webcache.googleusercontent.", "google.com/imgres", "/url?",
)


def _clean_google_url(href):
    """Google wraps some results as ``/url?q=<real>&...`` — unwrap that; pass real http(s)
    links through; drop everything else (internal nav, anchors)."""
    if not href:
        return None
    if href.startswith("/url?") or "google.com/url?" in href:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        return (params.get("q") or params.get("url") or [None])[0]
    if href.startswith("http"):
        return href
    return None


def _is_google_result(url):
    return bool(url) and url.startswith("http") and not any(b in url for b in _GOOGLE_BAD)


def _google_snippet(h3):
    block = h3.find_parent(class_=re.compile(r"\b(g|tF2Cxc|MjjYud|Gx5Zad)\b")) or h3.parent
    if block is None:
        return ""
    sn = block.select_one(".VwiC3b, .aCOpRe, .st, span.st, div[data-sncf], div[style*='line']")
    return _abs_text(sn)


def parse_google(html, count):
    soup = _soup(html)
    container = soup.select_one("#search, #rso, #center_col, #main")
    if container is None:
        raise ParseError("results container not found (#search/#rso/#main)")
    results, seen = [], set()
    for h3 in container.select("h3"):
        a = h3.find_parent("a", href=True) or h3.find_previous("a", href=True)
        url = _clean_google_url(a.get("href")) if a else None
        if not _is_google_result(url) or url in seen:
            continue
        seen.add(url)
        results.append({
            "title": _abs_text(h3, 300),
            "url": url,
            "snippet": _google_snippet(h3),
        })
        if len(results) >= count:
            break
    return results


# --------------------------------------------------------------------------- Bing
def parse_bing(html, count):
    soup = _soup(html)
    container = soup.select_one("#b_results, ol#b_results, #b_content")
    if container is None:
        raise ParseError("results container not found (#b_results)")
    results, seen = [], set()
    for li in container.select("li.b_algo"):
        a = li.select_one("h2 a[href], h2 > a")
        if not a or not a.get("href"):
            continue
        url = a["href"]
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        snippet = li.select_one(".b_caption p, .b_algoSlug, .b_lineclamp2, .b_lineclamp3, .b_caption")
        results.append({
            "title": _abs_text(a, 300),
            "url": url,
            "snippet": _abs_text(snippet),
        })
        if len(results) >= count:
            break
    return results


# --------------------------------------------------------------------------- DuckDuckGo
def _clean_ddg_url(href):
    """DDG HTML results link through ``//duckduckgo.com/l/?uddg=<encoded real url>``."""
    if not href:
        return None
    if "uddg=" in href:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        real = (params.get("uddg") or [None])[0]
        if real:
            return real
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    return None


def parse_duckduckgo(html, count):
    soup = _soup(html)
    container = soup.select_one(".results, #links, .serp__results")
    if container is None:
        raise ParseError("results container not found (.results/#links)")
    results, seen = [], set()
    for res in container.select("div.result, div.web-result"):
        if "result--ad" in (res.get("class") or []):
            continue
        a = res.select_one("a.result__a, h2 a[href]")
        url = _clean_ddg_url(a.get("href")) if a else None
        if not url or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        snippet = res.select_one("a.result__snippet, .result__snippet")
        results.append({
            "title": _abs_text(a, 300),
            "url": url,
            "snippet": _abs_text(snippet),
        })
        if len(results) >= count:
            break
    return results


# --------------------------------------------------------------------------- registry
def _q(query):
    return urllib.parse.quote_plus(query or "")


ENGINES = {
    "google": {
        "build_url": lambda q, n: f"https://www.google.com/search?q={_q(q)}&num={max(n, 10)}&hl=en",
        "parse": parse_google,
    },
    "bing": {
        "build_url": lambda q, n: f"https://www.bing.com/search?q={_q(q)}&count={max(n, 10)}&setlang=en",
        "parse": parse_bing,
    },
    "duckduckgo": {
        "build_url": lambda q, n: f"https://html.duckduckgo.com/html/?q={_q(q)}",
        "parse": parse_duckduckgo,
    },
}


def get_adapter(engine):
    adapter = ENGINES.get((engine or "").lower())
    if not adapter:
        raise ValueError(f"unknown engine '{engine}' (supported: {', '.join(SUPPORTED)})")
    return adapter


def build_url(engine, query, count):
    return get_adapter(engine)["build_url"](query, count)
