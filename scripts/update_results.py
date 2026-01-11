"""Atualiza resultados de apostas salvas no DB local.

Uso: python scripts/update_results.py [db_path]
"""
from rpa_scraper import fetch_html
import db
import sys
import re
from typing import Optional

sys.path.insert(0, '.')


def extract_score_from_html(html: str) -> Optional[tuple]:
    # try to find explicit final/FT markers first
    patterns = [
        r"(?:final|full time|ft)[^\d]{0,30}(\d{1,2})\s*[:\-–]\s*(\d{1,2})",
        r"(\d{1,2})\s*[:\-–]\s*(\d{1,2})\s*(?:final|ft)",
        r"title\W[^>]{0,200}(\d{1,2})\s*[:\-–]\s*(\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1)), int(m.group(2))
            except Exception:
                pass

    # fallback: first reasonable score appearance
    m2 = re.search(r"(\d{1,2})\s*[:\-–]\s*(\d{1,2})", html)
    if m2:
        try:
            return int(m2.group(1)), int(m2.group(2))
        except Exception:
            return None
    return None


def evaluate_market_against_score(market: str, home: int, away: int) -> Optional[bool]:
    """Return True if bet WON, False if LOST, None if unknown/unparsable."""
    txt = (market or '').lower()
    total = home + away
    # goals over/under
    m = re.search(r"over\s*([0-9]+(?:\.[05])?)", txt)
    if not m:
        m = re.search(r"([0-9]+(?:\.[05])?)\s*over", txt)
    if m:
        try:
            line = float(m.group(1))
            return total > line
        except Exception:
            return None

    m = re.search(r"under\s*([0-9]+(?:\.[05])?)", txt)
    if m:
        try:
            line = float(m.group(1))
            return total < line
        except Exception:
            return None

    # 1X2
    if '1x2' in txt or '1 x 2' in txt or re.search(r'\b1\b', txt) or re.search(r'\b2\b', txt):
        # try to detect selection digit
        if ' x ' in txt or ' draw ' in txt or ' empate ' in txt or 'x' == txt.strip():
            sel = 'X'
        elif '1' in txt and '2' not in txt:
            sel = '1'
        elif '2' in txt and '1' not in txt:
            sel = '2'
        else:
            # try exact patterns like '1', 'X', '2'
            m2 = re.search(r"\b(1|x|2)\b", txt)
            sel = m2.group(1).upper() if m2 else None
        if not sel:
            return None
        if home > away:
            winner = '1'
        elif home == away:
            winner = 'X'
        else:
            winner = '2'
        return winner == sel

    return None


def main():
    # Determine DB config: CLI arg may be a sqlite path or a config YAML path.
    db_arg = sys.argv[1] if len(sys.argv) > 1 else None
    db_config = None
    if db_arg and (db_arg.endswith('.yaml') or db_arg.endswith('.yml')):
        try:
            import yaml
            with open(db_arg, 'r', encoding='utf-8') as fh:
                cfg = yaml.safe_load(fh)
            db_config = cfg.get('db')
        except Exception:
            db_config = db_arg
    elif db_arg:
        # treat as sqlite path
        db_config = db_arg
    else:
        # try load default config.local.yaml
        try:
            import yaml
            with open('config.local.yaml', 'r', encoding='utf-8') as fh:
                cfg = yaml.safe_load(fh)
            db_config = cfg.get('db') or None
        except Exception:
            db_config = None

    pending = db.get_pending_bets(db_config=db_config)
    print(f"Encontradas {len(pending)} apostas pendentes em {db_config}")
    for b in pending:
        mid = b['id']
        murl = b.get('match_url') or b.get('match')
        if not murl:
            print(f"[{mid}] sem match_url, pulando")
            continue
        try:
            html = fetch_html(murl)
        except Exception as e:
            print(f"[{mid}] falha ao buscar {murl}: {e}")
            continue
        sc = extract_score_from_html(html)
        if not sc:
            print(f"[{mid}] score nao encontrado em {murl}")
            continue
        home, away = sc
        won = evaluate_market_against_score(b.get('market') or '', home, away)
        if won is None:
            print(
                f"[{mid}] nao foi possivel avaliar mercado '{b.get('market')}' com score {home}-{away}")
            continue
        status = 'WON' if won else 'LOST'
        db.update_bet_status(
            mid, status, result=f"{home}-{away}", db_config=db_config)
        print(f"[{mid}] atualizado para {status} (score {home}-{away})")

    s = db.stats(db_config=db_config)
    print('\n-- Estatísticas --')
    print(s)


if __name__ == '__main__':
    main()
