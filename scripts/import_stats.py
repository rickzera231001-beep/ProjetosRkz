import stats_db
import argparse
import json
import os
import glob
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


def import_folder(data_dir, db_path=None):
    stats_db.init_db(db_path)
    files = sorted(glob.glob(os.path.join(data_dir, '*.json')))
    summary = {'files': 0, 'raw_inserted': 0, 'matches_inserted': 0}
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print('Failed to load', fp, e)
            continue
        fname = os.path.basename(fp)
        stats_db.save_raw('local_file', fname, data, db_path=db_path)
        summary['files'] += 1
        summary['raw_inserted'] += 1
        # if this file contains matches, import them
        if isinstance(data, dict) and 'matches' in data:
            for m in data.get('matches', []):
                stats_db.save_match(m, db_path=db_path)
                summary['matches_inserted'] += 1
    return summary


def main():
    p = argparse.ArgumentParser(
        description='Import local JSON stats into stats DB')
    p.add_argument('--data-dir', default=os.path.join(os.path.dirname(__file__),
                   '..', 'data'), help='Data folder')
    p.add_argument('--db-path', default=None, help='Path to stats DB (sqlite)')
    args = p.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    if not os.path.isdir(data_dir):
        print('Data directory not found:', data_dir)
        return
    print('Importing JSON files from', data_dir)
    summary = import_folder(data_dir, db_path=args.db_path)
    print('Imported:', summary)


if __name__ == '__main__':
    main()
