"""Given a matches JSON (as produced by extract_paulistao_matches), fetch odds for each match from configured bookmakers and save.
Usage: python scripts/fetch_odds_for_matches.py --matches data/paulistao_matches.json
"""
from functools import partial
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
import yaml
import argparse
import json
from rpa_scraper import find_odds_for_match_on_bookmaker, scrape_betano_odds, scrape_superbet_odds
import os
import sys
# ensure repo root on path for imports
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

parser = argparse.ArgumentParser()
parser.add_argument('--matches', help='Matches json file',
                    default='data/paulistao_matches.json')
parser.add_argument('--out', help='Output file',
                    default='data/paulistao_odds.json')
parser.add_argument('--workers', type=int, default=8, help='Worker threads')
parser.add_argument('--fast', action='store_true',
                    help='Fast mode: avoid Playwright')
parser.add_argument('--cache', action='store_true',
                    help='Enable in-memory cache')
parser.add_argument('--profile', action='store_true', help='Print timing')
args = parser.parse_args()

if args.cache:
    from rpa_scraper import set_cache_enabled
    set_cache_enabled(True)
if args.fast:
    from rpa_scraper import set_fast_mode
    set_fast_mode(True)

if not os.path.exists(args.matches):
    raise SystemExit(f'Matches file not found: {args.matches}')

with open(args.matches, 'r', encoding='utf-8') as fh:
    matches_doc = json.load(fh)

# load config
cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config.local.yaml')
with open(cfg_path, 'r', encoding='utf-8') as fh:
    cfg = yaml.safe_load(fh)

bookmakers = [x for x in cfg.get('sites', []) if x.get('type') == 'bookmaker']

out = {'generated_at': __import__(
    'datetime').datetime.utcnow().isoformat(), 'matches': []}


start = time.time()

# process a single match in parallel


def process_one(m):
    url = m.get('url')
    home = m.get('home')
    away = m.get('away')
    print('\nFetching odds for', home, 'vs', away, url)
    markets = []
    for bm in bookmakers:
        base = bm.get('url')
        try:
            found = find_odds_for_match_on_bookmaker(
                {'source_url': url, 'home_team': home, 'away_team': away}, base)
            if found and found.get('markets'):
                for mk in found['markets']:
                    mk['bookmaker'] = bm.get('name')
                    markets.append(mk)
        except Exception as e:
            print('  homepage search error for', bm.get('name'), e)

        # try candidate direct pages for common bookies
        try:
            if 'betano' in base:
                for cand in [f"{base.rstrip('/')}/odds/{(home or '').lower().replace(' ', '-')}-{(away or '').lower().replace(' ', '-')}/"]:
                    try:
                        r = scrape_betano_odds(cand)
                        if r and r.get('markets'):
                            for mk in r['markets']:
                                mk['bookmaker'] = bm.get('name')
                                mk['source_url'] = cand
                                markets.append(mk)
                            break
                    except Exception:
                        continue
            if 'superbet' in base:
                for cand in [f"{base.rstrip('/')}/odds/futebol/{(home or '').lower().replace(' ', '-')}-x-{(away or '').lower().replace(' ', '-')}/"]:
                    try:
                        r = scrape_superbet_odds(cand)
                        if r and r.get('markets'):
                            for mk in r['markets']:
                                mk['bookmaker'] = bm.get('name')
                                mk['source_url'] = cand
                                markets.append(mk)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    # dedupe
    seen = set()
    dedup = []
    for mk in markets:
        key = (mk.get('market_type'), mk.get('selection'),
               float(mk.get('odd') or 0), mk.get('bookmaker'))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(mk)

    return {'url': url, 'home': home, 'away': away, 'markets': dedup}


with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = {ex.submit(process_one, m)
                         : m for m in matches_doc.get('matches', [])}
    for fut in as_completed(futures):
        try:
            mm = fut.result()
            out['matches'].append(mm)
        except Exception as e:
            print('Match worker error', e)

if args.profile:
    print('Elapsed', time.time() - start)

os.makedirs(os.path.dirname(args.out), exist_ok=True)
with open(args.out, 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)

# close playwright if available
try:
    from rpa_playwright import close_playwright
    close_playwright()
except Exception:
    pass

print('\nSaved odds to', args.out)
