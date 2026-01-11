from playwright.sync_api import sync_playwright

# Module-level reusable Playwright objects to avoid cold-starts
_playwright = None
_browser = None
_context = None


def _ensure_playwright(headless: bool = True):
    global _playwright, _browser, _context
    if _playwright is None:
        _playwright = sync_playwright().start()
    if _browser is None:
        _browser = _playwright.chromium.launch(
            headless=headless, args=["--no-sandbox"])
    if _context is None:
        _context = _browser.new_context()
    return _context


def close_playwright():
    """Close any open Playwright browser/context to free resources."""
    global _playwright, _browser, _context
    try:
        if _context:
            _context.close()
            _context = None
        if _browser:
            _browser.close()
            _browser = None
        if _playwright:
            _playwright.stop()
            _playwright = None
    except Exception:
        pass


def fetch_html_playwright(url: str, wait_for: str = None, timeout: int = 15000, headless: bool = True) -> str:
    """Fetch a page using Playwright and return the page content HTML.

    Reuses a single browser instance across calls to avoid expensive cold starts.

    wait_for: optional selector to wait for before returning content.
    timeout: milliseconds
    """
    ctx = _ensure_playwright(headless=headless)
    page = ctx.new_page()
    page.goto(url, timeout=timeout)
    if wait_for:
        try:
            page.wait_for_selector(wait_for, timeout=timeout)
        except Exception:
            pass
    html = page.content()
    try:
        page.close()
    except Exception:
        pass
    return html


def extract_markets_near_labels(url: str, labels: list, timeout: int = 15000, headless: bool = True) -> list:
    """Use Playwright to find occurrences of text labels and extract nearby numeric values (odds).

    Reuses the browser to improve performance.

    Returns list of dicts: {'label': label_text, 'odds': [{'text': matched_text, 'value': float, 'html': node_outerHTML}], 'source_url': url}
    """
    results = []
    ctx = _ensure_playwright(headless=headless)
    page = ctx.new_page()
    page.goto(url, timeout=timeout)

    # limit per-page search to avoid very expensive scans
    for label in labels:
        try:
            loc = page.locator(f"text={label}")
            count = loc.count()
        except Exception:
            count = 0
        for i in range(count):
            try:
                el = loc.nth(i)
                # evaluate in page: search nearby (container or parent subtree) for numeric tokens that look like odds
                js = r'''
(node) => {
  const res = [];
  const container = node.closest('[class*="market"], [class*="odd"], [class*="odds"], [class*="selection"], [class*="price"], [id*="market"]') || node.parentElement || node;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_ELEMENT, null, false);
  let hits = 0;
  while (walker.nextNode()) {
    try {
      const txt = (walker.currentNode.innerText || '').trim();
      const m = txt.match(/[0-9]{1,3}(?:[.,][0-9]{1,3})/);
      if (m) {
        res.push({text: m[0], html: walker.currentNode.outerHTML});
        hits++;
      }
    } catch (e) { continue; }
    if (hits > 8) break;
  }
  return res;
}
'''
                found = el.evaluate(js)
                parsed = []
                for item in found:
                    txt = item.get('text')
                    # normalize comma decimals
                    if txt and isinstance(txt, str):
                        try:
                            v = float(txt.replace(',', '.'))
                        except Exception:
                            continue
                        # coarse filter: plausible range for odds (narrower to avoid cookie/modal noise)
                        if 1.01 <= v <= 15:
                            parsed.append(
                                {'text': txt, 'value': v, 'html': item.get('html')})
                if parsed:
                    results.append(
                        {'label': label, 'odds': parsed, 'source_url': url})
            except Exception:
                continue
    try:
        page.close()
    except Exception:
        pass
    return results
