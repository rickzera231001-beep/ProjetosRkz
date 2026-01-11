"""Quick tester to run Betano & Superbet extraction for existing matches and dump results.
Usage: python scripts/test_bookmakers_extraction.py --matches data/paulistao_matches.json --out data/paulistao_odds_new.json
"""
from rpa_scraper import scrape_betano_odds, scrape_superbet_odds, set_fast_mode, set_cache_enabled, clear_cache
import re
import json
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
# ensure project root is on path (must happen before local imports)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

parser = argparse.ArgumentParser()
parser.add_argument('--matches', default='data/paulistao_matches.json')
parser.add_argument('--out', default='data/paulistao_odds_new.json')
parser.add_argument('--workers', type=int, default=8,
                    help='Number of worker threads')
parser.add_argument('--fast', action='store_true',
                    help='Fast mode: avoid Playwright fallbacks')
parser.add_argument('--cache', action='store_true',
                    help='Enable in-memory cache for fetched pages')
parser.add_argument('--profile', action='store_true',
                    help='Print timing information')
args = parser.parse_args()

if args.cache:
    set_cache_enabled(True)
if args.fast:
    set_fast_mode(True)
else:
    set_fast_mode(False)

with open(args.matches) as f:
    src = json.load(f)

out = {'generated_at': None, 'matches': []}

# helper to slugify


def slug(s):
    t = re.sub(r"[^a-z0-9\- ]", '', s.lower())
    return t.replace(' ', '-')

# process a single match (run per worker)


def process_match(m):
    mm = {'url': m.get('url'), 'home': m.get('home'),
          'away': m.get('away'), 'markets': []}
    home = mm.get('home') or ''
    away = mm.get('away') or ''
    names = [home, away]
    b_urls = []
    for n in names:
        if not n:
            continue
        s = slug(n)
        b_urls.append(f"https://www.betano.bet.br/odds/comparar-equipes-{s}/")
        b_urls.append(
            f"https://superbet.bet.br/odds/futebol/comparar-equipes-x-{s}/")
    b_urls = list(dict.fromkeys(b_urls))
    local_markets = []
    for bu in b_urls:
        try:
            if 'betano' in bu:
                res = scrape_betano_odds(bu)
            else:
                res = scrape_superbet_odds(bu)
            for mk in res.get('markets', []):
                mk['source_url'] = bu
                local_markets.append(mk)
        except Exception as e:
            print('Error scraping', bu, e)
    mm['markets'] = local_markets
    return mm


start = time.time()
with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = {ex.submit(process_match, m): m for m in src.get('matches', [])}
    for fut in as_completed(futures):
        try:
            mm = fut.result()
            out['matches'].append(mm)
        except Exception as e:
            print('Match worker error', e)

if args.profile:
    print('Elapsed:', time.time() - start)

out['generated_at'] = __import__('datetime').datetime.utcnow().isoformat()
with open(args.out, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# try to close Playwright if used
try:
    from rpa_playwright import close_playwright
    close_playwright()
except Exception:
    pass

print('Saved', args.out)
