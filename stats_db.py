import sqlite3
import json
import os
from datetime import datetime


def get_conn(db_path=None):
    if not db_path:
        db_path = os.environ.get('STATS_DB_PATH', 'stats.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS raw_data (
        id INTEGER PRIMARY KEY,
        source TEXT,
        filename TEXT,
        loaded_at TEXT,
        data TEXT
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY,
        name TEXT,
        slug TEXT UNIQUE
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY,
        source_url TEXT UNIQUE,
        date TEXT,
        home TEXT,
        away TEXT,
        home_goals INTEGER,
        away_goals INTEGER,
        raw TEXT
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS team_stats (
        id INTEGER PRIMARY KEY,
        team TEXT,
        season TEXT,
        matches_played INTEGER,
        wins INTEGER,
        draws INTEGER,
        losses INTEGER,
        goals_for INTEGER,
        goals_against INTEGER,
        raw TEXT,
        UNIQUE(team, season)
    )
    """
    )
    conn.commit()
    return conn


def save_raw(source, filename, data, db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO raw_data (source, filename, loaded_at, data) VALUES (?, ?, ?, ?)",
        (source, filename, datetime.utcnow().isoformat(),
         json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()


def save_match(match_dict, db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    src = match_dict.get('url') or match_dict.get('source_url')
    date = match_dict.get('date')
    home = match_dict.get('home')
    away = match_dict.get('away')
    home_goals = match_dict.get('home_goals')
    away_goals = match_dict.get('away_goals')
    raw = json.dumps(match_dict, ensure_ascii=False)
    try:
        cur.execute(
            "INSERT OR IGNORE INTO matches (source_url, date, home, away, home_goals, away_goals, raw) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (src, date, home, away, home_goals, away_goals, raw),
        )
        conn.commit()
    finally:
        cur.close()


def list_raw(limit=20, db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source, filename, loaded_at FROM raw_data ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in cur.fetchall()]


def get_matches(db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM matches ORDER BY date DESC")
    return [dict(r) for r in cur.fetchall()]


def get_team_stats(team, season=None, db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    if season:
        cur.execute(
            "SELECT * FROM team_stats WHERE team = ? AND season = ?", (team, season))
    else:
        cur.execute(
            "SELECT * FROM team_stats WHERE team = ? ORDER BY season DESC LIMIT 1", (team,))
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_team_stats(team, season, stats_dict, db_path=None):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO team_stats (team, season, matches_played, wins, draws, losses, goals_for, goals_against, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(team, season) DO UPDATE SET matches_played=excluded.matches_played, wins=excluded.wins, draws=excluded.draws, losses=excluded.losses, goals_for=excluded.goals_for, goals_against=excluded.goals_against, raw=excluded.raw",
        (
            team,
            season,
            stats_dict.get('matches_played', 0),
            stats_dict.get('wins', 0),
            stats_dict.get('draws', 0),
            stats_dict.get('losses', 0),
            stats_dict.get('goals_for', 0),
            stats_dict.get('goals_against', 0),
            json.dumps(stats_dict, ensure_ascii=False),
        ),
    )
    conn.commit()


if __name__ == '__main__':
    print('Initializing stats DB...')
    conn = init_db()
    print('Initialized', conn)
