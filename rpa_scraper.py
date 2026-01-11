import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# Simple runtime modes/caches to speed up repeated runs
_FAST_MODE = False
_CACHE_ENABLED = False
_html_cache = {}


def set_fast_mode(val: bool):
    global _FAST_MODE
    _FAST_MODE = bool(val)


def set_cache_enabled(val: bool):
    global _CACHE_ENABLED
    _CACHE_ENABLED = bool(val)


def clear_cache():
    global _html_cache
    _html_cache = {}


def fetch_html(url: str, timeout: int = 10, use_cache: bool = True) -> str:
    """Try to fetch using requests first; if it fails with 403 or other server-side block,
    fallback to Playwright headless browser to retrieve dynamic content.

    When _FAST_MODE is enabled, do NOT fallback to Playwright and prefer cached/requests-only path.
    """
    import time
    if use_cache and _CACHE_ENABLED and url in _html_cache:
        return _html_cache[url]

    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        text = resp.text
        # quick check for bot-block pages
        if resp.status_code == 200 and ("access denied" in text.lower() or "forbidden" in text.lower()):
            raise requests.HTTPError("Possibly blocked by site (custom check)")
        if use_cache and _CACHE_ENABLED:
            _html_cache[url] = text
        return text
    except requests.HTTPError as e:
        # try Playwright fallback unless fast mode is enabled
        if _FAST_MODE:
            raise
        try:
            from rpa_playwright import fetch_html_playwright
        except Exception:
            raise
        try:
            html = fetch_html_playwright(url)
            if use_cache and _CACHE_ENABLED:
                _html_cache[url] = html
            return html
        except Exception:
            raise e
    except Exception:
        # any other error, re-raise to let caller handle/log
        raise


def extract_with_selector(soup: BeautifulSoup, selector: str):
    if not selector:
        return None
    el = soup.select_one(selector)
    if not el:
        return None
    return el.get_text(strip=True)


def parse_number(text: str):
    if text is None:
        return None
    # remove common non-numeric characters
    t = text.replace('%', '').replace(',', '.').strip()
    try:
        return float(t)
    except Exception:
        return None


def scrape_stats(url: str, selectors: Dict[str, str]) -> Dict[str, Any]:
    """Scrape simple statistics from a page using CSS selectors.

    selectors: mapping like {'team_name': '.team .name', 'win_rate': '.win-rate'}
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    result: Dict[str, Any] = {}
    for key, sel in (selectors or {}).items():
        text = extract_with_selector(soup, sel)
        num = parse_number(text)
        result[key] = num if num is not None else text

    # If no selectors provided, try some sensible defaults (team name from h1/title)
    if not result:
        title = None
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            title = h1.get_text(strip=True)
        if not title:
            t = soup.title
            if t and t.get_text(strip=True):
                title = t.get_text(strip=True)
        if title:
            result["team_name"] = title
    return result


def scrape_multiple(url: str, field_selectors: Dict[str, str]):
    return scrape_stats(url, field_selectors)


def extract_team_urls_from_sofascore_league(url: str, max_teams: int = 20):
    """Return a list of team page URLs found on a SofaScore league/tournament page.

    Strategy: look for anchor hrefs with '/team/' and return absolute URLs (deduped).
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    teams = []
    for a in anchors:
        href = a["href"]
        if "/team/" in href:
            # make absolute
            if href.startswith("/"):
                full = "https://www.sofascore.com" + href
            elif href.startswith("http"):
                full = href
            else:
                full = "https://www.sofascore.com/" + href
            teams.append(full)
    # dedupe preserving order
    seen = set()
    out = []
    for t in teams:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= max_teams:
            break
    return out


def extract_match_urls_from_sofascore_league(url: str, max_matches: int = 50):
    """Return a list of match page URLs found on a SofaScore league/tournament page.

    Strategy: look for anchor hrefs with '/match/' and return absolute URLs (deduped).
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)
    matches = []
    for a in anchors:
        href = a["href"]
        if "/match/" in href:
            if href.startswith("/"):
                full = "https://www.sofascore.com" + href
            elif href.startswith("http"):
                full = href
            else:
                full = "https://www.sofascore.com/" + href
            matches.append(full)
    # dedupe preserving order
    seen = set()
    out = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            out.append(m)
        if len(out) >= max_matches:
            break
    return out


def get_match_date_from_match_page(url: str):
    """Attempt to extract a date (YYYY-MM-DD) from a match page.

    Tries:
    - <time datetime="..."> tag
    - ISO-like timestamps in page scripts
    Returns a date string 'YYYY-MM-DD' or None if not found.
    """
    import re
    from datetime import datetime

    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # 1) look for <time datetime="...">
    time_tag = soup.find("time")
    if time_tag and time_tag.has_attr("datetime"):
        try:
            dt = datetime.fromisoformat(
                time_tag["datetime"].replace("Z", "+00:00"))
            return dt.date().isoformat()
        except Exception:
            pass

    # 2) search for ISO timestamps in scripts
    iso_re = re.compile(r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
    m = iso_re.search(html)
    if m:
        try:
            dt = datetime.fromisoformat(m.group(1))
            return dt.date().isoformat()
        except Exception:
            pass

    # 3) try to find dates like '10 Jan 2026'
    date_re = re.compile(r"(\d{1,2}\s+[A-Za-z]{3,}\s+20\d{2})")
    m2 = date_re.search(html)
    if m2:
        try:
            dt = datetime.strptime(m2.group(1), "%d %b %Y")
            return dt.date().isoformat()
        except Exception:
            pass

    return None


def scrape_odds(url: str, selectors: Dict[str, str]) -> Dict[str, Any]:
    """Scrape market odds. Expect selectors like {'odds_home': '.odds .home', ...}
    Returns parsed floats where possible.
    """
    return scrape_stats(url, selectors)


# precompiled patterns for speed
_ODD_PATTERN = re.compile(r"\b([0-9]{1,2}(?:\.[0-9]{1,3})?)\b")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[\s\S]*?<\\1>", re.IGNORECASE)


def _find_odds_in_html(html: str):
    # quick cleanup: remove script/style blocks to avoid extracting numeric CSS/JS tokens
    if not html:
        return []
    cleaned = _SCRIPT_STYLE_RE.sub(' ', html)
    o = []
    for m in _ODD_PATTERN.finditer(cleaned):
        try:
            val = float(m.group(1))
            if 1.01 <= val <= 100.0:
                o.append((m.start(1), val))
        except Exception:
            pass
    return o


def sanitize_markets(markets: list) -> list:
    """Clean and validate market records extracted from bookmaker pages.

    Rules:
    - odd must be numeric and in reasonable range (1.01 .. 25)
    - discard contexts containing cookie/banner/head/script noise
    - add 'context_text' cleaned plain-text snippet
    - validate 1X2 groups: require complete triple and reasonable implied probability sum
    """
    from bs4 import BeautifulSoup
    cleaned = []
    for m in (markets or []):
        try:
            v = float(m.get('odd'))
        except Exception:
            continue
        # basic numeric clamp
        if not (1.01 <= v <= 25):
            continue
        ctx = (m.get('context') or '').lower()
        # discard obvious noise
        if any(bad in ctx for bad in ('onetrust', 'cookie', '<head', '<script', 'meta charset')):
            continue
        # discard CSS/banner-like captures: width/px/%/z-index are signs we grabbed style instead of odds
        if any(css in ctx for css in ('width:', 'px', '%', 'z-index', 'otFloatingRoundedCorner')):
            continue
        # derive a text snippet for grouping/inspection but avoid expensive parsing for huge contexts
        try:
            snippet = m.get('context', '')
            if len(snippet) > 1000:
                snippet = snippet[:1000]
            text = BeautifulSoup(
                snippet, 'html.parser').get_text(' ', strip=True)
            m['context_text'] = text[:200]
        except Exception:
            m['context_text'] = (m.get('context') or '')[:200]
        cleaned.append(m)

    # Validate 1X2 groups: keep only complete triples with sane implied probability
    groups = {}
    for m in cleaned:
        if m.get('market_type') == '1X2':
            key = m.get('context_text', '') or m.get('context', '')
            groups.setdefault(key, []).append(m)
    to_remove = set()
    for g in groups.values():
        if len(g) >= 3:
            try:
                odds = [float(x['odd']) for x in g]
                if any(o <= 1.05 for o in odds) or sum(1.0 / o for o in odds) > 1.9:
                    for x in g:
                        to_remove.add(id(x))
            except Exception:
                for x in g:
                    to_remove.add(id(x))
        else:
            # incomplete 1X2 - drop
            for x in g:
                to_remove.add(id(x))

    cleaned2 = [m for m in cleaned if id(m) not in to_remove]
      # attempt to further classify GENERIC markets by inspecting context_text
      import re

       def _classify(m):
            if m.get('market_type') and m.get('market_type') != 'GENERIC':
                return m
            txt = (m.get('context_text') or m.get('context') or '').lower()
            if not txt:
                return m
            # look for corners/escanteios
            if 'escante' in txt or 'corner' in txt:
                # find numeric line (like 3.5 or 3)
                mo = re.search(r"([0-9]+(?:\.[05])?)", txt)
                if mo:
                    line = float(mo.group(1))
                    # decide over/under by presence of words
                    if 'over' in txt or 'mais' in txt or '>' in txt:
                        m['market_type'] = 'CORNERS_OVER'
                        m['line'] = line
                    elif 'under' in txt or 'menos' in txt or '<' in txt:
                        m['market_type'] = 'CORNERS_UNDER'
                        m['line'] = line
                    else:
                        # default to OVER if only a number present
                        m['market_type'] = 'CORNERS_OVER'
                        m['line'] = line
                else:
                    m['market_type'] = 'CORNERS'
            # look for goals/total
            elif 'gol' in txt or 'total' in txt or 'over' in txt or 'under' in txt:
                mo = re.search(r"([0-9]+(?:\.[05])?)", txt)
                if mo:
                    line = float(mo.group(1))
                    if 'over' in txt or 'mais' in txt or '>' in txt:
                        m['market_type'] = 'GOALS_OVER'
                        m['line'] = line
                    elif 'under' in txt or 'menos' in txt or '<' in txt:
                        m['market_type'] = 'GOALS_UNDER'
                        m['line'] = line
                    else:
                        m['market_type'] = 'GOALS_OVER'
                        m['line'] = line
                else:
                    m['market_type'] = 'GOALS'
            # try detect 1X2 patterns like '1 x 2' nearby
            elif re.search(r"\b1\s*x\s*2\b", txt) or re.search(r"\b1x2\b", txt):
                # if odds grouped elsewhere, leave selection empty; mark market_type
                m['market_type'] = '1X2'
            return m

        cleaned3 = []
        for m in cleaned2:
            try:
                cleaned3.append(_classify(m))
            except Exception:
                cleaned3.append(m)
        return cleaned3
    return cleaned2


def scrape_betano_odds(url: str) -> Dict[str, Any]:
    """Generic odds extractor for Betano pages using Playwright DOM extraction when possible.
    Tries to extract structured markets: 1X2, Over/Under (e.g. over 2.5) and specifically goals/corners.
    Returns a mapping {'markets': [{'market_type', 'selection','odd', 'context'}, ...]}
    """
    res = {"markets": []}
    labels = ['Total de gols', 'Total gols', 'Total', 'Over',
              'Under', 'Escanteios', 'Escanteio', 'Corners']

    # Try Playwright DOM-run extraction for label-based markets
    try:
        from rpa_playwright import extract_markets_near_labels
        found = extract_markets_near_labels(url, labels)
        for block in found:
            ltxt = block.get('label', '').lower()
            if 'escante' in ltxt or 'corner' in ltxt:
                mtype = 'CORNERS'
            elif 'gol' in ltxt or 'total' in ltxt or 'over' in ltxt or 'under' in ltxt:
                mtype = 'GOALS'
            else:
                mtype = 'GENERIC'
            for o in block.get('odds', []):
                val = o.get('value')
                if val is None:
                    continue
                if val >= 1.01 and val <= 50:
                    res['markets'].append({'market_type': mtype, 'selection': None, 'odd': val, 'context': o.get(
                        'html'), 'source_url': url, 'bookmaker': 'Betano_Market'})
    except Exception:
        pass

    # If Playwright did not surface label-based markets, fallback to HTML heuristics for 1X2 and OU
    try:
        from rpa_playwright import fetch_html_playwright
        html = fetch_html_playwright(url)
    except Exception:
        html = fetch_html(url)

    import re
    # find 1X2 sequences
    seq_re = re.compile(
        r"(?:1\D{0,8}([0-9]+(?:\.[0-9]+)?)\D{0,8}X\D{0,8}([0-9]+(?:\.[0-9]+)?)\D{0,8}2\D{0,8}([0-9]+(?:\.[0-9]+)?))", re.IGNORECASE)
    for m in seq_re.finditer(html):
        try:
            o1 = float(m.group(1))
            ox = float(m.group(2))
            o2 = float(m.group(3))
            ctx = html[max(0, m.start()-60):m.end()+60]
            res['markets'].append(
                {'market_type': '1X2', 'selection': '1', 'odd': o1, 'context': ctx, 'bookmaker': 'Betano_Market'})
            res['markets'].append(
                {'market_type': '1X2', 'selection': 'X', 'odd': ox, 'context': ctx, 'bookmaker': 'Betano_Market'})
            res['markets'].append(
                {'market_type': '1X2', 'selection': '2', 'odd': o2, 'context': ctx, 'bookmaker': 'Betano_Market'})
        except Exception:
            pass

    # Over/Under patterns
    ou_re = re.compile(
        r"((?:total(?: de)?\s*(?:gols|escanteios?)|over|under|mais de|menos de|total))\s*[:\-]??\s*([0-9]+(?:\.[05])?)\D{0,12}([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE)
    for m in ou_re.finditer(html):
        try:
            label = m.group(1).lower()
            line = m.group(2)
            odd = float(m.group(3))
            ctx = html[max(0, m.start()-80):m.end()+80]
            if 'escante' in label or 'corner' in label:
                mtype = 'CORNERS'
            elif 'gol' in label or 'goal' in label:
                mtype = 'GOALS'
            else:
                mtype = 'OVER' if 'over' in label or 'mais' in label else 'UNDER'
            res['markets'].append(
                {'market_type': mtype, 'selection': line, 'odd': odd, 'context': ctx, 'bookmaker': 'Betano_Market'})
        except Exception:
            pass

    # Also search for explicit 'Escanteios' labels and numeric candidates nearby
    label_re = re.compile(r"(escanteios?|corners?)", re.IGNORECASE)
    for m in label_re.finditer(html):
        try:
            ctx_start = max(0, m.start()-80)
            ctx_end = min(len(html), m.end()+200)
            ctx = html[ctx_start:ctx_end]
            odds = _find_odds_in_html(ctx)
            for pos, val in odds:
                if val >= 1.01 and val <= 50:
                    res['markets'].append(
                        {'market_type': 'CORNERS', 'selection': None, 'odd': val, 'context': ctx, 'bookmaker': 'Betano_Market'})
        except Exception:
            pass

    # Fallback: generic odds
    if not res['markets']:
        odds = _find_odds_in_html(html)
        seen = set()
        for pos, val in odds:
            if val in seen:
                continue
            seen.add(val)
            ctx = html[max(0, pos-40):pos+40]
            res['markets'].append(
                {'market_type': 'GENERIC', 'selection': None, 'odd': val, 'context': ctx, 'bookmaker': 'Betano_Market'})

    # sanitize markets before returning
    res['markets'] = sanitize_markets(res['markets'])
    return res


def scrape_superbet_odds(url: str) -> Dict[str, Any]:
    """Odds extractor for Superbet; prefer Playwright DOM-based extraction to reliably capture goals/corners markets."""
    res = {'markets': []}
    labels = ['Total de gols', 'Total gols', 'Total', 'Over', 'Under',
              'Escanteios', 'Escanteio', 'Corners', 'Escanteios totais']
    try:
        from rpa_playwright import extract_markets_near_labels
        found = extract_markets_near_labels(url, labels)
        for block in found:
            ltxt = block.get('label', '').lower()
            if 'escante' in ltxt or 'corner' in ltxt:
                mtype = 'CORNERS'
            elif 'gol' in ltxt or 'total' in ltxt or 'over' in ltxt or 'under' in ltxt:
                mtype = 'GOALS'
            else:
                mtype = 'GENERIC'
            for o in block.get('odds', []):
                val = o.get('value')
                if val is None:
                    continue
                if val >= 1.01 and val <= 50:
                    res['markets'].append({'market_type': mtype, 'selection': None, 'odd': val, 'context': o.get(
                        'html'), 'source_url': url, 'bookmaker': 'Superbet_Market'})
    except Exception:
        # fallback to HTML scanning
        try:
            html = fetch_html(url)
            import re
            for label in (r'total de gols', r'total gols', r'total', r'over|under', r'escanteios?', r'corners?'):
                for m in re.finditer(label, html, re.IGNORECASE):
                    ctx_start = max(0, m.start()-80)
                    ctx_end = min(len(html), m.end()+200)
                    ctx = html[ctx_start:ctx_end]
                    odds = _find_odds_in_html(ctx)
                    for pos, val in odds:
                        if val >= 1.01 and val <= 50:
                            ltxt = m.group(0).lower()
                            if 'escante' in ltxt or 'corner' in ltxt:
                                mtype = 'CORNERS'
                            elif 'gol' in ltxt or 'total' in ltxt or 'over' in ltxt or 'under' in ltxt:
                                mtype = 'GOALS'
                            else:
                                mtype = 'GENERIC'
                            res['markets'].append(
                                {'market_type': mtype, 'selection': None, 'odd': val, 'context': ctx, 'source_url': url, 'bookmaker': 'Superbet_Market'})
        except Exception:
            pass

    # if still nothing found, fallback to Betano-like scan
    if not res['markets']:
        try:
            return scrape_betano_odds(url)
        except Exception:
            return {'markets': []}
    # sanitize markets
    res['markets'] = sanitize_markets(res['markets'])
    return res


def find_odds_for_match_on_bookmaker(match: Dict[str, Any], bookmaker_url: str) -> Dict[str, Any]:
    """Attempt to find odds for a given match on a bookmaker page.

    Heuristic: fetch the bookmaker page, search for team names (from match info) and capture odds nearby.
    Returns {'markets': [{'name', 'odd', 'context', 'match':match_url_or_names}]}
    """
    html = fetch_html(bookmaker_url)
    # build search terms from match (team names or match_url)
    names = []
    if match.get('source_url'):
        # try to parse team names from URL last segments
        parts = match['source_url'].rstrip('/').split('/')
        if parts:
            names.append(parts[-1].replace('-', ' '))
    # also look for obvious fields
    for k in ['home_team', 'away_team', 'team_name', 'match_name']:
        v = match.get(k)
        if v:
            names.append(v)
    # dedupe and lowercase
    terms = [t.strip().lower() for t in names if t]
    terms = list(dict.fromkeys(terms))

    # try to recover team names if placeholders found or terms empty
    if any('comparar' in t for t in terms) or not terms:
        try:
            real = parse_match_teams_from_match_page(
                match.get('url') or match.get('source_url') or '')
            if real and len(real) >= 2:
                terms = [real[0].strip().lower(), real[1].strip().lower()]
        except Exception:
            pass

    found = {"markets": []}
    if not terms:
        # fallback: extract all odds but return structured list
        return {'markets': [{'market_type': 'GENERIC', 'selection': None, 'odd': v, 'context': '', 'bookmaker': 'Unknown'} for _, v in _find_odds_in_html(html)]}

    # scan for occurrences of team names and extract nearest odds
    import re
    for term in terms:
        for m in re.finditer(re.escape(term), html, re.IGNORECASE):
            pos = m.start()
            window_start = max(0, pos - 300)
            window_end = min(len(html), pos + 300)
            ctx = html[window_start:window_end]

            # Prefer explicit goals/escanteios labels near the team occurrence
            label_re = re.compile(
                r"(total de gols|total gols|over|under|mais de|menos de|escanteios?|corners?)", re.IGNORECASE)
            lmatch = label_re.search(ctx)
            if lmatch:
                # extract odds near label
                ctx2_start = max(0, window_start + lmatch.start() - 60)
                ctx2_end = min(len(html), window_start + lmatch.end() + 160)
                ctx2 = html[ctx2_start:ctx2_end]
                odds = _find_odds_in_html(ctx2)
                for _, val in odds:
                    if val >= 1.01 and val <= 50:
                        ltxt = lmatch.group(0).lower()
                        if 'escante' in ltxt or 'corner' in ltxt:
                            mtype = 'CORNERS'
                        elif 'gol' in ltxt or 'over' in ltxt or 'under' in ltxt or 'total' in ltxt:
                            mtype = 'GOALS'
                        else:
                            mtype = 'GENERIC'
                        found['markets'].append(
                            {'market_type': mtype, 'selection': None, 'odd': val, 'context': ctx2, 'match': match.get('source_url')})
                # continue to next occurrence
                continue

            # fallback to any odds in the window
            odds = _find_odds_in_html(ctx)
            for _, val in odds:
                if val >= 1.01 and val <= 100:
                    found['markets'].append({'market_type': 'GENERIC', 'selection': None,
                                            'odd': val, 'context': ctx, 'match': match.get('source_url')})

    # sanitize found markets and return
    found['markets'] = sanitize_markets(found['markets'])
    return found

    # dedupe by odd+name
    seen = set()
    out = []
    for m in found['markets']:
        key = (m.get('name'), m.get('odd'))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return {'markets': out}


def _normalize_label(label: str) -> str:
    import unicodedata
    if not label:
        return label
    txt = label.strip().lower()
    txt = unicodedata.normalize('NFKD', txt).encode(
        'ascii', 'ignore').decode('ascii')
    return txt


def parse_match_teams_from_match_page(url: str) -> list:
    """Attempt to extract home/away team names from a SofaScore match page or similar.

    Returns list [home, away] or empty list if not found.
    """
    try:
        html = fetch_html(url)
    except Exception:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    title = None
    h1 = soup.find('h1')
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    if not title:
        t = soup.title
        if t and t.get_text(strip=True):
            title = t.get_text(strip=True)
    if not title:
        return []
    # try common separators
    import re
    sep_patterns = [r'\s+vs\s+', r'\s+v\s+',
                    r'\s+-\s+', r'\s+x\s+', r'\s+–\s+']
    for pat in sep_patterns:
        m = re.split(pat, title, flags=re.IGNORECASE)
        if len(m) == 2:
            return [m[0].strip(), m[1].strip()]
    # fallback split on ' – '
    parts = title.split('–')
    if len(parts) == 2:
        return [parts[0].strip(), parts[1].strip()]

    # fallback: try to extract team anchors from page
    teams_map = extract_team_urls_from_match_page(url)
    if teams_map:
        names = list(teams_map.keys())
        if len(names) >= 2:
            return [names[0], names[1]]

    return []


def extract_team_urls_from_match_page(url: str) -> dict:
    """Return a mapping of team display name -> team URL found on a SofaScore match page.

    This helps locate team pages to scrape team-level stats when R10Score lacks data.
    """
    try:
        html = fetch_html(url)
    except Exception:
        return {}
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    anchors = soup.find_all('a', href=True)
    res = {}
    for a in anchors:
        href = a['href']
        txt = a.get_text(strip=True)
        if not txt:
            continue
        if '/team/' in href:
            if href.startswith('/'):
                full = 'https://www.sofascore.com' + href
            elif href.startswith('http'):
                full = href
            else:
                full = 'https://www.sofascore.com/' + href
            res[txt] = full

    # If no team anchors found in static HTML, try a Playwright-rendered page and re-parse
    if not res:
        try:
            from rpa_playwright import fetch_html_playwright
            rendered = fetch_html_playwright(url, wait_for='a')
            soup2 = BeautifulSoup(rendered, 'html.parser')
            for a in soup2.find_all('a', href=True):
                href = a['href']
                txt = a.get_text(strip=True)
                if not txt:
                    continue
                if '/team/' in href:
                    if href.startswith('/'):
                        full = 'https://www.sofascore.com' + href
                    elif href.startswith('http'):
                        full = href
                    else:
                        full = 'https://www.sofascore.com/' + href
                    res[txt] = full
        except Exception:
            pass

    return res


def scrape_sofascore_team_stats(url: str) -> Dict[str, Any]:
    """Scrape approximate per-game stats from a SofaScore team page.

    Tries to find labels/numbers indicating averages for 'gols', 'escanteios', 'chutes' etc.
    Returns a dict with normalized keys like 'goals_per_game', 'corners_per_game', 'shots_per_game'.
    """
    try:
        html = fetch_html(url)
    except Exception:
        # fallback: try Playwright rendered
        try:
            from rpa_playwright import fetch_html_playwright
            html = fetch_html_playwright(url)
        except Exception:
            return {}
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    out: Dict[str, Any] = {}
    import re

    # Look for explicit labels with nearby numeric values
    kv_re = re.compile(
        r"([A-Za-zÀ-ÖØ-öø-ÿ\s]{3,40})[:\-]?\s*([0-9]+(?:[\.,][0-9]+)?)", re.IGNORECASE)
    for tag in soup.find_all(['p', 'span', 'div', 'li', 'td', 'th']):
        text = tag.get_text(" ", strip=True)
        for m in kv_re.finditer(text):
            label = m.group(1).strip().lower()
            val = m.group(2).replace(',', '.')
            try:
                f = float(val)
            except Exception:
                continue
            if 'escante' in label or 'corner' in label:
                out['corners_per_game'] = f
            elif 'gol' in label or 'goal' in label:
                out['goals_per_game'] = f
            elif 'chute' in label or 'shot' in label:
                out['shots_per_game'] = f
            elif 'falta' in label:
                out['fouls_per_game'] = f

    # also check for compact widgets that show numbers nearby known class names
    # try to find elements that contain the word 'Média' and a nearby number
    # Limit scanning of 'Média' occurrences to avoid expensive DOM traversals
    max_hits = 30
    hits = 0
    for el in soup.find_all(string=lambda s: s and 'média' in s.lower()):
        hits += 1
        if hits > max_hits:
            break
        try:
            parent = el.parent
            if not parent:
                continue
            txt = parent.get_text(" ", strip=True)
        except Exception:
            continue
        nums = re.findall(r"([0-9]+(?:[\.,][0-9]+)?)", txt)
        for n in nums:
            try:
                f = float(n.replace(',', '.'))
            except Exception:
                continue
            # attempt to classify by context
            ctx = txt.lower()
            if 'gols' in ctx or 'gol' in ctx:
                out.setdefault('goals_per_game', f)
            elif 'escante' in ctx:
                out.setdefault('corners_per_game', f)
            elif 'chute' in ctx:
                out.setdefault('shots_per_game', f)

    return out


def scrape_r10_stats(url: str) -> Dict[str, Any]:
    """Scrape statistics from r10score pages.

    Strategy: attempt to find tables, definition lists, or label:value pairs; parse numbers and return a flat dict of stats.
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    out: Dict[str, Any] = {}

    # 1) parse tables with two columns
    tables = soup.find_all('table')
    for table in tables:
        for tr in table.find_all('tr'):
            tds = tr.find_all(['td', 'th'])
            if len(tds) >= 2:
                label = tds[0].get_text(strip=True)
                val = tds[1].get_text(strip=True)
                labeln = _normalize_label(label)
                num = parse_number(val)
                out[labeln] = num if num is not None else val

    # 2) parse definition lists dt/dd
    for dl in soup.find_all('dl'):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True)
            val = dd.get_text(strip=True)
            labeln = _normalize_label(label)
            num = parse_number(val)
            out[labeln] = num if num is not None else val

    # 3) parse pairs like 'Escanteios: 4.5' in paragraphs/spans
    import re
    kv_re = re.compile(r"([A-Za-zÀ-ÖØ-öø-ÿ0-9\s]+)[:\-]\s*([0-9.,%]+)")
    for tag in soup.find_all(['p', 'span', 'div', 'li']):
        text = tag.get_text(" ", strip=True)
        for m in kv_re.finditer(text):
            label = m.group(1)
            val = m.group(2)
            labeln = _normalize_label(label)
            num = parse_number(val)
            out[labeln] = num if num is not None else val

    # If nothing found, try Playwright-rendered HTML (single-page app) and re-parse
    if not out:
        try:
            from rpa_playwright import fetch_html_playwright
            html2 = fetch_html_playwright(url)
            soup2 = BeautifulSoup(html2, "html.parser")

            # 1) parse tables with two columns
            tables = soup2.find_all('table')
            for table in tables:
                for tr in table.find_all('tr'):
                    tds = tr.find_all(['td', 'th'])
                    if len(tds) >= 2:
                        label = tds[0].get_text(strip=True)
                        val = tds[1].get_text(strip=True)
                        labeln = _normalize_label(label)
                        num = parse_number(val)
                        out[labeln] = num if num is not None else val

            # 2) parse definition lists dt/dd
            for dl in soup2.find_all('dl'):
                dts = dl.find_all('dt')
                dds = dl.find_all('dd')
                for dt, dd in zip(dts, dds):
                    label = dt.get_text(strip=True)
                    val = dd.get_text(strip=True)
                    labeln = _normalize_label(label)
                    num = parse_number(val)
                    out[labeln] = num if num is not None else val

            # 3) parse pairs like 'Escanteios: 4.5' in paragraphs/spans
            import re
            kv_re = re.compile(r"([A-Za-zÀ-ÖØ-öø-ÿ0-9\s]+)[:\-]\s*([0-9.,%]+)")
            for tag in soup2.find_all(['p', 'span', 'div', 'li']):
                text = tag.get_text(" ", strip=True)
                for m in kv_re.finditer(text):
                    label = m.group(1)
                    val = m.group(2)
                    labeln = _normalize_label(label)
                    num = parse_number(val)
                    out[labeln] = num if num is not None else val

        except Exception:
            pass

    # If still nothing found, fall back to extracting title
    if not out:
        h1 = soup.find('h1')
        if h1:
            out['page_title'] = h1.get_text(strip=True)

    return out
