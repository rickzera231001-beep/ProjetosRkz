import sqlite3
from typing import List, Dict, Any, Optional, Tuple
import datetime
import os


def _open_sqlite(path: str):
    conn = sqlite3.connect(path)
    return conn, 'sqlite'


def _open_postgres(cfg: Dict[str, Any]):
    try:
        import psycopg2
    except Exception as e:
        raise RuntimeError(
            "psycopg2 is required for Postgres support: pip install psycopg2-binary") from e
    conn = psycopg2.connect(host=cfg.get('host', 'localhost'), port=cfg.get('port', 5432), user=cfg.get(
        'user'), password=cfg.get('password'), dbname=cfg.get('database') or cfg.get('db'))
    return conn, 'pg'


def _open_mysql(cfg: Dict[str, Any]):
    try:
        import pymysql
    except Exception as e:
        raise RuntimeError(
            "pymysql is required for MySQL support: pip install pymysql") from e
    conn = pymysql.connect(host=cfg.get('host', 'localhost'), port=int(cfg.get('port', 3306)), user=cfg.get(
        'user'), password=cfg.get('password'), database=cfg.get('database') or cfg.get('db'), charset='utf8mb4')
    return conn, 'my'


def _get_conn(db_config) -> Tuple[Any, str]:
    # db_config may be None, a string path, or a dict with type
    if not db_config:
        path = os.getenv('DB_PATH', 'bets.db')
        return _open_sqlite(path)
    if isinstance(db_config, str):
        return _open_sqlite(db_config)
    if isinstance(db_config, dict):
        t = db_config.get('type', 'sqlite').lower()
        if t in ('sqlite', 'file'):
            path = db_config.get('path') or os.getenv('DB_PATH', 'bets.db')
            return _open_sqlite(path)
        if t in ('postgres', 'postgresql', 'pg'):
            return _open_postgres(db_config)
        if t in ('mysql', 'mariadb'):
            return _open_mysql(db_config)
    # fallback
    return _open_sqlite('bets.db')


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bets (
    id SERIAL PRIMARY KEY,
    match TEXT,
    market TEXT,
    bookmaker TEXT,
    odd REAL,
    delta REAL,
    created_at TEXT,
    status TEXT DEFAULT 'PENDING',
    result TEXT,
    match_url TEXT
)
"""


def init_db(db_config=None):
    conn, kind = _get_conn(db_config)
    cur = conn.cursor()
    try:
        cur.execute(_CREATE_TABLE_SQL)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def save_candidates(cands: List[Dict[str, Any]], db_config=None):
    if not cands:
        return
    conn, kind = _get_conn(db_config)
    cur = conn.cursor()
    try:
        now = datetime.datetime.utcnow().isoformat()
        if kind == 'sqlite':
            sql = "INSERT INTO bets (match, market, bookmaker, odd, delta, created_at, match_url) VALUES (?,?,?,?,?,?,?)"
        else:
            sql = "INSERT INTO bets (match, market, bookmaker, odd, delta, created_at, match_url) VALUES (%s,%s,%s,%s,%s,%s,%s)"
        for c in cands:
            match = c.get('match')
            market = c.get('market')
            bookmaker = c.get('bookmaker')
            odd = float(c.get('odd') or 0)
            delta = float(c.get('delta') or 0)
            match_url = c.get('match_url') or c.get('match')
            cur.execute(sql, (match, market, bookmaker,
                        odd, delta, now, match_url))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_pending_bets(db_config=None) -> List[Dict[str, Any]]:
    conn, kind = _get_conn(db_config)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, match, market, bookmaker, odd, delta, created_at, status, result, match_url FROM bets WHERE status='PENDING'")
        rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({
                'id': r[0], 'match': r[1], 'market': r[2], 'bookmaker': r[3], 'odd': r[4], 'delta': r[5], 'created_at': r[6], 'status': r[7], 'result': r[8], 'match_url': r[9]
            })
        return out
    finally:
        cur.close()
        conn.close()


def update_bet_status(bet_id: int, status: str, result: Optional[str] = None, db_config=None):
    conn, kind = _get_conn(db_config)
    cur = conn.cursor()
    try:
        if kind == 'sqlite':
            cur.execute("UPDATE bets SET status=?, result=? WHERE id=?",
                        (status, result, bet_id))
        else:
            cur.execute(
                "UPDATE bets SET status=%s, result=%s WHERE id=%s", (status, result, bet_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def stats(db_config=None) -> Dict[str, Any]:
    conn, kind = _get_conn(db_config)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM bets")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM bets WHERE status='WON'")
        won = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM bets WHERE status='LOST'")
        lost = cur.fetchone()[0]
        pct = (won / total * 100.0) if total else 0.0
        return {'total': total, 'won': won, 'lost': lost, 'pct_won': pct}
    finally:
        cur.close()
        conn.close()
