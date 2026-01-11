"""Fetch data from SofaScore internal API (best-effort) and save as CSV/JSON.

Usage examples:
  python scripts/fetch_sofascore_api.py --match-url "https://www.sofascore.com/...#id:15176506" --out out.json
  python scripts/fetch_sofascore_api.py --local --out out.csv

The script attempts to call api.sofascore.com endpoints for event details. If network
is unavailable or calls fail, use `--local` to build a DataFrame from local `data/` JSON files.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
try:
    import pandas as pd
except Exception:
    pd = None

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'


def extract_event_id(sofa_url: str):
    # try fragment id:15176506
    m = re.search(r'id:(\d+)', sofa_url)
    if m:
        return m.group(1)
    # else take last path segment if numeric
    parts = sofa_url.rstrip('/').split('/')
    if parts:
        last = parts[-1]
        if last.isdigit():
            return last
        # sometimes slug+id
        m2 = re.search(r'([a-z0-9]+)-?(\d+)$', last)
        if m2:
            return m2.group(2)
    return None


def fetch_event_api(event_id: str, session=None, timeout=10):
    session = session or requests.Session()
    url = f'https://api.sofascore.com/api/v1/event/{event_id}'
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; fetcher/1.0)', 'Accept': 'application/json'}
    resp = session.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def normalize_event_json(ev_json):
    # Flatten useful fields into a DataFrame-friendly dict
    try:
        event = ev_json.get('event') or ev_json
    except Exception:
        event = ev_json
    row = {
        'id': event.get('id'),
        'title': event.get('title'),
        'home_name': None,
        'away_name': None,
        'startTimestamp': event.get('startTimestamp'),
        'sport': ev_json.get('sport') if isinstance(ev_json, dict) else None,
    }
    try:
        home = event.get('homeTeam') or event.get('home')
        away = event.get('awayTeam') or event.get('away')
        if home:
            row['home_name'] = home.get('name')
        if away:
            row['away_name'] = away.get('name')
    except Exception:
        pass
    return row


def local_matches_dataframe():
    # read data/paulistao_matches.json or other JSON files and build a list of dicts
    candidates = []
    for fp in DATA_DIR.glob('*.json'):
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                j = json.load(f)
        except Exception:
            continue
        if isinstance(j, dict) and 'matches' in j:
            for m in j.get('matches', []):
                candidates.append({
                    'source_file': fp.name,
                    'url': m.get('url'),
                    'date': m.get('date'),
                    'home': m.get('home'),
                    'away': m.get('away'),
                })
    if not candidates:
        raise SystemExit('No local match files found in data/')
    if pd:
        return pd.DataFrame(candidates)
    return candidates


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        '--match-url', help='SofaScore match URL (can include #id:15176506)')
    p.add_argument('--event-id', help='SofaScore event id')
    p.add_argument('--local', action='store_true',
                   help='Build DataFrame from local data/ files')
    p.add_argument(
        '--out', help='Output path (json or csv). Defaults to stdout for json')
    args = p.parse_args()

    if args.local:
        df = local_matches_dataframe()
        if args.out:
            outp = Path(args.out)
            if outp.suffix.lower() == '.csv':
                if pd and isinstance(df, pd.DataFrame):
                    df.to_csv(outp, index=False)
                else:
                    # write CSV manually
                    import csv
                    keys = df[0].keys()
                    with open(outp, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, keys)
                        writer.writeheader()
                        writer.writerows(df)
            else:
                with open(outp, 'w', encoding='utf-8') as f:
                    json.dump(df if not pd else json.loads(df.to_json(
                        orient='records', force_ascii=False)), f, ensure_ascii=False, indent=2)
            print('Saved local matches to', outp)
        else:
            if pd and isinstance(df, pd.DataFrame):
                print(df.to_json(orient='records', force_ascii=False))
            else:
                print(json.dumps(df, ensure_ascii=False))
        return

    event_id = args.event_id
    if not event_id and args.match_url:
        event_id = extract_event_id(args.match_url)
    if not event_id:
        print('No event id provided. Use --match-url or --event-id or --local')
        return

    try:
        j = fetch_event_api(event_id)
    except Exception as e:
        print('API fetch failed:', e)
        print('Try running with --local to use local data/ files')
        return

    row = normalize_event_json(j)
    df = pd.json_normalize(row)
    if args.out:
        outp = Path(args.out)
        if outp.suffix.lower() == '.csv':
            df.to_csv(outp, index=False)
        else:
            with open(outp, 'w', encoding='utf-8') as f:
                json.dump(j, f, ensure_ascii=False, indent=2)
        print('Saved API data to', outp)
    else:
        print(df.to_json(orient='records', force_ascii=False))


if __name__ == '__main__':
    main()
