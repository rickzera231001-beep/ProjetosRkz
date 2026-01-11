from ai_eval import _detect_market_from_context
import os
import json
from glob import glob
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


def analyze_folder(folder='data/raw_markets'):
    files = glob(os.path.join(folder, '*.json'))
    report = []
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                j = json.load(f)
        except Exception:
            continue
        match = j.get('source_url') or j.get('match_url') or fp
        markets = j.get('markets') or []
        for m in markets:
            res = _detect_market_from_context(m) or {}
            report.append({'file': os.path.basename(
                fp), 'match': match, 'market': m, 'detected': res})
    return report


def main():
    rep = analyze_folder()
    good = [r for r in rep if r['detected']]
    print(
        f"Analyzed {len(rep)} markets from {len(set([r['file'] for r in rep]))} files. Detected: {len(good)}")
    for r in good[:200]:
        print(r['file'], r['detected'], r['market'].get('odd'))


if __name__ == '__main__':
    main()
