"""Fix matches by inferring teams from URL slug when home/away placeholders are present.
Usage: python scripts/fix_matches_using_slugs.py --matches data/paulistao_matches.json --out data/paulistao_matches_fixed.json
"""
import json
import argparse
import os, sys
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
    home = m.get('home') or ''
    away = m.get('away') or ''
    if 'comparar' in home.lower() or 'comparar' in away.lower():
        try:
            slug = url.split('/match/')[1].split('/')[0].lower()
            parts = slug.split('-')
            if len(parts) >= 2:
                split = max(1, len(parts) // 2)
                left = '-'.join(parts[:split])
                right = '-'.join(parts[split:])
                if 'comparar' in home.lower():
                    m['home'] = left.replace('-', ' ').title()
                if 'comparar' in away.lower():
                    m['away'] = right.replace('-', ' ').title()
                print('Inferred', url, '->', [m['home'], m['away']])
        except Exception as e:
            print('Err', e)

with open(args.out, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('Saved', args.out)
