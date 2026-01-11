"""Extract Paulistão football match URLs and basic metadata and save to JSON.
Usage: python scripts/extract_paulistao_matches.py --dates 11.01.2026,12.01.2026
"""
import unicodedata
from rpa_scraper import extract_match_urls_from_sofascore_league, get_match_date_from_match_page
import os
import sys
import json
import yaml
import argparse
from datetime import datetime, date, timedelta

# allow running from repo root
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

# Load config
cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config.local.yaml')
with open(cfg_path, 'r', encoding='utf-8') as fh:
    cfg = yaml.safe_load(fh)


# Get Paulistão league (normalize accents)

def _norm(s: str) -> str:
    if not s:
        return ''
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


league = None
for lg in cfg.get('leagues', []):
    if lg.get('name') and 'paulista' in _norm(lg.get('name')):
        league = lg
        break
if not league:
    raise SystemExit('Paulistão não configurado em config.local.yaml')

parser = argparse.ArgumentParser()
parser.add_argument(
    '--dates', help='Comma-separated dates (YYYY-MM-DD or DD.MM.YYYY)')
parser.add_argument('--out', help='Output file',
                    default='data/paulistao_matches.json')
args = parser.parse_args()

# build allowed set
allowed = set()
if args.dates:
    for s in args.dates.split(','):
        s = s.strip()
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                allowed.add(datetime.strptime(s, fmt).date().isoformat())
                break
            except Exception:
                continue
    if not allowed:
        raise SystemExit('Nenhuma data válida em --dates')
else:
    days = int(cfg.get('match_filter', {}).get('days_ahead', 1))
    for d in range(days + 1):
        allowed.add((date.today() + timedelta(days=d)).isoformat())

print('Allowed dates:', sorted(list(allowed)))

lg_url = league['url']
print('Discovering matches from', lg_url)
match_urls = extract_match_urls_from_sofascore_league(lg_url, max_matches=400)
print('Found', len(match_urls), 'raw match links')

# Keep only football
match_urls = [u for u in match_urls if '/football/' in u]
print('Filtered to', len(match_urls), 'football links')

# collect metadata
out = []
for u in match_urls:
    try:
        mdate = get_match_date_from_match_page(u)
    except Exception:
        mdate = None
    if not mdate or mdate not in allowed:
        continue
    # only keep match URL and date (do not attempt to parse team names)
    rec = {'url': u, 'date': mdate}
    out.append(rec)

print('Kept', len(out), 'matches for dates')
# ensure output dir
os.makedirs(os.path.dirname(args.out), exist_ok=True)
with open(args.out, 'w', encoding='utf-8') as fh:
    json.dump({'generated_at': datetime.utcnow().isoformat(), 'dates': sorted(
        list(allowed)), 'matches': out}, fh, ensure_ascii=False, indent=2)

print('Saved', args.out)
