"""Fix team names in data/paulistao_matches.json by parsing match pages on SofaScore.
Usage: python scripts/fix_pa_matches_team_names.py --matches data/paulistao_matches.json --out data/paulistao_matches_fixed.json
"""
from rpa_scraper import parse_match_teams_from_match_page
import json
import argparse
import os
import sys
# ensure project root on path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

parser = argparse.ArgumentParser()
parser.add_argument('--matches', default='data/paulistao_matches.json')
parser.add_argument('--out', default='data/paulistao_matches_fixed.json')
args = parser.parse_args()

with open(args.matches) as f:
    src = json.load(f)

out = src.copy()
for m in out['matches']:
    url = m.get('url')
    if not url:
        continue
    try:
        names = parse_match_teams_from_match_page(url)
        if names and len(names) >= 2:
            home_name, away_name = names[0], names[1]
            # If home is a placeholder like 'Comparar equipes', try to infer from URL slug
            if home_name and 'comparar' in home_name.lower():
                try:
                    slug = url.split('/match/')[1].split('/')[0].lower()
                    away_slug = away_name.lower().replace(' ', '-')
                    if slug.endswith(away_slug):
                        home_slug = slug[:-(len(away_slug)+1)]
                        home_name = home_slug.replace('-', ' ').title()
                except Exception:
                    pass
            # If still placeholders, try splitting slug into two halves
            if ('comparar' in (home_name or '').lower()) or ('comparar' in (away_name or '').lower()):
                try:
                    slug = url.split('/match/')[1].split('/')[0].lower()
                    parts = slug.split('-')
                    if len(parts) >= 2:
                        split = max(1, len(parts) // 2)
                        left = '-'.join(parts[:split])
                        right = '-'.join(parts[split:])
                        if 'comparar' in (home_name or '').lower():
                            home_name = left.replace('-', ' ').title()
                        if 'comparar' in (away_name or '').lower():
                            away_name = right.replace('-', ' ').title()
                except Exception:
                    pass
            m['home'] = home_name
            m['away'] = away_name
            print('Fixed', url, '->', [home_name, away_name])
    except Exception as e:
        print('Err parsing', url, e)

with open(args.out, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('Saved', args.out)
