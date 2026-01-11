from datetime import datetime
import argparse
import sys
import os
import unicodedata
from datetime import date, timedelta
import re
import json
from ai_eval import evaluate_markets_for_match, _norm_name
from rpa_scraper import extract_match_urls_from_sofascore_league, get_match_date_from_match_page, parse_match_teams_from_match_page, find_odds_for_match_on_bookmaker, scrape_betano_odds, scrape_superbet_odds, fetch_html
import yaml
import os
import sys
# ensure project root is on path for imports
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
# ensure project root is on path for imports when running from workspace root
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

# Load config
cfg_path = 'config.local.yaml'
with open(cfg_path, 'r', encoding='utf-8') as fh:
    cfg = yaml.safe_load(fh)


def _normalize(s: str) -> str:
    if not s:
        return ''
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


league = None
for lg in cfg.get('leagues', []):
    if lg.get('name') and 'paulista' in _normalize(lg.get('name')):
        league = lg
        break
if not league:
    raise SystemExit('Paulistão não configurado em config.local.yaml')

lg_url = league['url']
print('Discovering matches from', lg_url)
match_urls = extract_match_urls_from_sofascore_league(lg_url, max_matches=200)
print('Found', len(match_urls), 'raw match links')
# filter only football matches (exclude basketball, etc.)
orig_count = len(match_urls)
match_urls = [u for u in match_urls if '/football/' in u]
print('Kept', len(match_urls),
      'football match links (removed', orig_count - len(match_urls), ')')

# Filter dates: support explicit --dates (comma-separated, ISO or dd.mm.YYYY) or fallback to match_filter.days_ahead

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    '--dates', help='Comma-separated dates (YYYY-MM-DD or DD.MM.YYYY)')
args, _ = parser.parse_known_args()

if args.dates:
    allowed = set()
    for s in args.dates.split(','):
        s = s.strip()
        d = None
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except Exception:
                continue
        if d:
            allowed.add(d.isoformat())
    if not allowed:
        raise SystemExit('Nenhuma data válida encontrada em --dates')
else:
    days = int(cfg.get('match_filter', {}).get('days_ahead', 1))
    allowed = set()
    for d in range(days + 1):
        allowed.add((date.today() + timedelta(days=d)).isoformat())

print('Filtering for dates:', sorted(list(allowed)))

kept = []
for mu in match_urls:
    try:
        mdate = get_match_date_from_match_page(mu)
        if not mdate:
            continue
        if mdate in allowed:
            kept.append(mu)
    except Exception:
        continue
print('Kept', len(kept), 'matches after date filter')

# prepare bookmakers
bookmakers = [x for x in cfg.get('sites', []) if x.get('type') == 'bookmaker']

# helper: create candidate bookmaker URLs from team names


def slugify(s: str) -> str:
    t = s.strip().lower()
    t = re.sub(r"[^a-z0-9]+", '-', t)
    t = re.sub(r"-+", '-', t).strip('-')
    return t


def candidate_urls_for_bookmaker(base: str, home: str, away: str):
    base = base.rstrip('/')
    h = slugify(home)
    a = slugify(away)
    cands = []
    # Betano pattern
    cands.append(f"{base}/odds/{h}-{a}/")
    # Superbet pattern
    cands.append(f"{base}/odds/futebol/{h}-x-{a}/")
    # generic fallback
    cands.append(f"{base}/odds/{h}_vs_{a}/")
    return cands


# evaluate each match
value_margin = float(cfg.get('value_detection', {}).get('value_margin', 0.03))
min_odd = float(cfg.get('value_detection', {}).get('min_odd_for_leg', 1.1))
max_odd = float(cfg.get('value_detection', {}).get('max_odd_for_leg', 2.0))


def report_for_match(mu: str):
    print('\n---')
    print('Match:', mu)
    teams = parse_match_teams_from_match_page(mu)
    if not teams or len(teams) < 2:
        print('  could not parse teams from match page')
        return None
    home, away = teams[0], teams[1]
    print('  teams:', home, 'vs', away)

    # build a match object container
    match = {'source_url': mu}

    all_markets = []
    # 1) try homepage search for each bookmaker
    for bm in bookmakers:
        try:
            found = find_odds_for_match_on_bookmaker(
                {'source_url': mu, 'home_team': home, 'away_team': away}, bm.get('url'))
            if found and found.get('markets'):
                for m in found['markets']:
                    m['bookmaker'] = bm.get('name')
                    all_markets.append(m)
        except Exception as e:
            print('  homepage search error for', bm.get('name'), e)

    # 2) try candidate URLs (direct match pages)
    for bm in bookmakers:
        base = bm.get('url')
        cands = candidate_urls_for_bookmaker(base, home, away)
        for c in cands:
            try:
                if 'betano' in base:
                    res = scrape_betano_odds(c)
                elif 'superbet' in base:
                    res = scrape_superbet_odds(c)
                else:
                    # generic scraper
                    res = find_odds_for_match_on_bookmaker(
                        {'source_url': mu, 'home_team': home, 'away_team': away}, base)
                if res and res.get('markets'):
                    for m in res['markets']:
                        m['bookmaker'] = bm.get('name')
                        m['source_url'] = c
                        all_markets.append(m)
                    # if found markets for this candidate, stop trying more candidates for this bm
                    break
            except Exception as e:
                # ignore and try next
                continue

    # dedupe markets by (market_type, selection, odd, bookmaker)
    seen = set()
    dedup = []
    for m in all_markets:
        key = (m.get('market_type'), str(m.get('selection')),
               float(m.get('odd') or 0), m.get('bookmaker'))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(m)

    print('  collected markets:', len(dedup))

    # build team stats map using SofaScore team pages
    from rpa_scraper import extract_team_urls_from_match_page, scrape_sofascore_team_stats
    team_urls = extract_team_urls_from_match_page(mu)
    team_stats_map = {}
    if team_urls:
        for disp, url in team_urls.items():
            nk = _norm_name(disp)
            s = scrape_sofascore_team_stats(url)
            if s:
                team_stats_map[nk] = s

    # prepare match object with collected markets
    match['markets'] = dedup
    # evaluate
    legs = evaluate_markets_for_match(
        match, team_stats_map, value_margin=value_margin)

    # filter to goals/corners only and also by odd bounds
    interesting = [l for l in legs if ('GOALS' in l.get('market') or 'CORNERS' in l.get(
        'market')) and l['odd'] >= min_odd and l['odd'] <= max_odd]

    if not interesting:
        print('  No value legs found for goals/escanteios with margin', value_margin)
        return {'match': mu, 'home': home, 'away': away, 'legs': []}

    print('  Value legs found:')
    for l in interesting:
        print('   -', l['market'], 'odd=', l['odd'], 'delta=', round(l['delta'], 3),
              'bookmaker=', l.get('bookmaker'), 'source_url=', l.get('match') or l.get('source_url'))

    return {'match': mu, 'home': home, 'away': away, 'legs': interesting}


results = []
for mu in kept:
    r = report_for_match(mu)
    if r:
        results.append(r)

# Save report
out = {'generated_at': __import__(
    'datetime').datetime.utcnow().isoformat(), 'matches': results}
with open('paulistao_value_report.json', 'w', encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print('\nSaved paulistao_value_report.json with',
      len(results), 'matches containing value legs')
