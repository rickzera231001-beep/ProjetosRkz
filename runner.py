import os
import yaml
from typing import List, Dict, Any

from rpa_scraper import scrape_stats, scrape_odds
from ai_eval import evaluate_matches


def load_config(path: str = "config.local.yaml") -> Dict[str, Any]:
    if os.path.exists(path):
        cfg_path = path
    else:
        cfg_path = "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    cfg = load_config()
    sites = cfg.get("sites", [])
    collected: List[Dict[str, Any]] = []

    for s in sites:
        name = s.get("name")
        url = s.get("url")
        stats_sel = s.get("stats_selectors") or {}
        odds_sel = s.get("odds_selectors") or {}
        try:
            if stats_sel:
                stats = scrape_stats(url, stats_sel)
                stats["source_name"] = name
                stats["source_url"] = url
                collected.append(stats)
            if odds_sel:
                odds = scrape_odds(url, odds_sel)
                odds["source_name"] = name
                odds["source_url"] = url
                collected.append(odds)
        except Exception as e:
            # Save HTML sample for inspection when scraping fails
            print(f"Erro scraping {name} ({url}): {e}")
            saved = False
            # First try Playwright fallback (better for sites that block requests)
            try:
                from rpa_playwright import fetch_html_playwright
                print(f"Tentando fallback com Playwright para {url} ...")
                sample = fetch_html_playwright(url)
                fname = f"scrape_error_{name}.html"
                with open(fname, "w", encoding="utf-8") as fh:
                    fh.write(sample)
                print(f"Amostra HTML (Playwright) salva em {fname}")
                saved = True
            except Exception as e2:
                print(f"Falha no fallback Playwright: {e2}")
                # Try requests-based fetch as last resort
                try:
                    from rpa_scraper import fetch_html
                    sample = fetch_html(url)
                    fname = f"scrape_error_{name}.html"
                    with open(fname, "w", encoding="utf-8") as fh:
                        fh.write(sample)
                    print(f"Amostra HTML (requests) salva em {fname}")
                    saved = True
                except Exception as e3:
                    err_fname = f"scrape_error_{name}.txt"
                    with open(err_fname, "w", encoding="utf-8") as fh:
                        fh.write(
                            f"Initial error: {e}\n\nPlaywright error: {e2}\n\nrequests error: {e3}\n")
                    print(
                        f"Falha ao salvar amostra HTML. Detalhes escritos em {err_fname}")
                    print(
                        "Se o Playwright não estiver instalado, execute: pip install playwright && playwright install")

    # Process configured leagues (discover teams on SofaScore and scrape them)
    leagues = cfg.get("leagues", [])
    if leagues:
        from rpa_scraper import extract_team_urls_from_sofascore_league
        for lg in leagues:
            if lg.get("source") != "sofascore":
                continue
            lg_name = lg.get("name")
            lg_url = lg.get("url")
            max_teams = lg.get("max_teams", 20)
            print(f"Descobrindo times para a liga {lg_name} ({lg_url}) ...")
            try:
                team_urls = extract_team_urls_from_sofascore_league(
                    lg_url, max_teams=max_teams)
                print(
                    f"Encontrados {len(team_urls)} times (limit {max_teams}).")
                # skipping per-team scraping to focus only on league matches (Paulistão)
            except Exception as e:
                print(f"Erro descobrindo times em {lg_name}: {e}")

            # Discover matches and filter by date (today + days_ahead)
            match_filter = cfg.get(
                "match_filter", {"type": "upcoming", "days_ahead": 1})
            allowed_dates = None
            if match_filter and match_filter.get("type") == "upcoming":
                from datetime import date, timedelta
                days = int(match_filter.get("days_ahead", 1))
                allowed = set()
                for d in range(days + 1):
                    allowed.add((date.today() + timedelta(days=d)).isoformat())
                allowed_dates = allowed
                print(
                    f"Filtrando partidas para datas: {sorted(list(allowed_dates))}")

            try:
                from rpa_scraper import extract_match_urls_from_sofascore_league, get_match_date_from_match_page, find_odds_for_match_on_bookmaker
                match_urls = extract_match_urls_from_sofascore_league(
                    lg_url, max_matches=300)
                print(
                    f"Encontradas {len(match_urls)} partidas na página da liga (raw).")
                kept = 0
                for mu in match_urls:
                    try:
                        mdate = get_match_date_from_match_page(mu)
                        if not mdate:
                            continue
                        if allowed_dates and mdate not in allowed_dates:
                            continue
                        # fetch basic match info
                        try:
                            info = scrape_stats(mu, {})
                        except Exception:
                            info = {"match_url": mu}
                        info["match_date"] = mdate
                        info["source_name"] = f"{lg_name} - match"
                        info["source_url"] = mu

                        # collect odds from bookmakers configured in sites
                        bookmakers = [x for x in cfg.get(
                            'sites', []) if x.get('type') == 'bookmaker']
                        markets = []
                        for bm in bookmakers:
                            try:
                                bm_url = bm.get('url')
                                # attempt bookmaker-specific direct match page construction for better match hits
                                direct_markets = None
                                try:
                                    from rpa_scraper import parse_match_teams_from_match_page, scrape_betano_odds, scrape_superbet_odds

                                    teams = parse_match_teams_from_match_page(mu) or [
                                    ]

                                    def _slug(s: str) -> str:
                                        import unicodedata
                                        import re
                                        if not s:
                                            return ''
                                        t = unicodedata.normalize('NFKD', s).encode(
                                            'ascii', 'ignore').decode('ascii')
                                        t = t.lower()
                                        t = re.sub(r"[^a-z0-9]+",
                                                   '-', t).strip('-')
                                        return t

                                    if teams and len(teams) >= 2:
                                        home = _slug(teams[0])
                                        away = _slug(teams[1])
                                        # Betano pattern: /odds/<home>-<away>/<id>/
                                        if 'betano' in (bm.get('name') or '').lower() or 'betano' in (bm_url or ''):
                                            cand = bm_url.rstrip(
                                                '/') + f"/odds/{home}-{away}/"
                                            try:
                                                found = scrape_betano_odds(
                                                    cand)
                                                if found and found.get('markets'):
                                                    direct_markets = found['markets']
                                            except Exception:
                                                direct_markets = direct_markets
                                        # Superbet pattern: /odds/futebol/<home>-x-<away>-<id>/
                                        if 'superbet' in (bm.get('name') or '').lower() or 'superbet' in (bm_url or ''):
                                            cand = bm_url.rstrip(
                                                '/') + f"/odds/futebol/{home}-x-{away}/"
                                            try:
                                                found = scrape_superbet_odds(
                                                    cand)
                                                if found and found.get('markets'):
                                                    direct_markets = found['markets']
                                            except Exception:
                                                direct_markets = direct_markets
                                except Exception:
                                    direct_markets = None

                                if direct_markets:
                                    for mk in direct_markets:
                                        mk['bookmaker'] = bm.get('name')
                                        markets.append(mk)
                                    continue

                                # fallback: generic find on bookmaker site
                                found = find_odds_for_match_on_bookmaker(
                                    info, bm_url)
                                if found and found.get('markets'):
                                    for mk in found['markets']:
                                        mk['bookmaker'] = bm.get('name')
                                        markets.append(mk)
                            except Exception as e:
                                print(
                                    f"Erro coletando odds em {bm.get('name')}: {e}")
                        if markets:
                            info['markets'] = markets

                        collected.append(info)
                        kept += 1
                    except Exception as e:
                        print(f"Erro ao processar partida {mu}: {e}")
                print(f"Mantidas {kept} partidas filtradas por data.")
            except Exception as e:
                print(f"Erro descobrindo partidas em {lg_name}: {e}")

    use_openai = cfg.get("openai", {}).get("use_openai", False)
    api_key = cfg.get("openai", {}).get(
        "api_key") or os.getenv("OPENAI_API_KEY")

    results = evaluate_matches(
        collected, use_openai=use_openai, openai_api_key=api_key)

    print("\n--- Recomendações / Scores ---\n")
    for r in results:
        print(r)

    # collect detected value legs from the evaluation results
    value_margin = float(
        cfg.get('value_detection', {}).get('value_margin', 0.05))
    min_odd = float(cfg.get('value_detection', {}).get('min_odd_for_leg', 1.1))
    max_odd = float(cfg.get('value_detection', {}).get('max_odd_for_leg', 2.0))

    all_value_legs = []
    for r in results:
        legs = r.get('legs') or []
        for l in legs:
            delta = l.get('delta')
            odd = l.get('odd')
            try:
                oddf = float(odd)
            except Exception:
                continue
            if delta is None or delta < value_margin:
                continue
            if oddf < min_odd or oddf > max_odd:
                continue
            candidate = {'odd': oddf, 'delta': float(
                delta) if delta is not None else 0.0, 'market': None, 'bookmaker': None, 'match': None}
            m = l.get('market')
            if isinstance(m, dict):
                candidate['market'] = m.get(
                    'name') or m.get('market_name') or str(m)
                candidate['bookmaker'] = m.get(
                    'bookmaker') or m.get('source') or None
            else:
                candidate['market'] = str(m)

            # try to infer bookmaker/market from the parent result markets
            if (not candidate.get('bookmaker')) and r.get('markets'):
                for mk in r['markets']:
                    try:
                        mk_odd = float(
                            mk.get('odd') or mk.get('market_odds') or 0)
                        if abs(mk_odd - oddf) < 1e-6:
                            candidate['bookmaker'] = mk.get(
                                'bookmaker') or mk.get('source_name')
                            candidate['market'] = mk.get('name') or mk.get(
                                'market_name') or candidate['market']
                            break
                    except Exception:
                        continue

            candidate['match'] = r.get('source_url') or r.get(
                'match_url') or r.get('team_name') or r.get('source_name')
            all_value_legs.append(candidate)

    # generate parlays from detected value legs
    from ai_eval import generate_parlays
    parlays = generate_parlays(all_value_legs, target=cfg.get('value_detection', {}).get('parlay_target', 2.0), max_legs=int(cfg.get(
        'value_detection', {}).get('max_parlay_legs', 3)), allow_cross_game=bool(cfg.get('value_detection', {}).get('allow_cross_game', True)))

    print("\n--- Parlays sugeridos ---\n")
    for p in parlays[:20]:
        print({'odd': p['odd'], 'total_delta': p['total_delta'], 'legs': [
              {'odd': l['odd'], 'market': l['market'], 'bookmaker': l.get('bookmaker'), 'match': l.get('match')} for l in p['legs']]})

    # Persist detected candidate legs into configured DB (supports sqlite/postgres/mysql)
    try:
        import db
        db_config = cfg.get('db') or None
        db.init_db(db_config)
        # ensure match_url present
        for c in all_value_legs:
            if not c.get('match_url'):
                c['match_url'] = c.get('match')
        db.save_candidates(all_value_legs, db_config=db_config)
        target_desc = db_config if db_config else 'bets.db'
        print(f"Salvos {len(all_value_legs)} candidatos em {target_desc}")
    except Exception as e:
        print(f"Falha ao salvar candidatos no DB: {e}")

    # Write JSON output if configured
    out_path = cfg.get('output', {}).get('json_file')
    if out_path:
        import json
        payload = {'generated_at': __import__('datetime').datetime.utcnow(
        ).isoformat(), 'results': results, 'parlays': []}
        for p in parlays:
            payload['parlays'].append({'odd': p['odd'], 'total_delta': p['total_delta'], 'legs': [{'odd': float(
                l['odd']), 'market': l['market'], 'bookmaker': l.get('bookmaker'), 'match': l.get('match')} for l in p['legs']]})
        with open(out_path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"Saída JSON salva em {out_path}")


if __name__ == "__main__":
    main()
