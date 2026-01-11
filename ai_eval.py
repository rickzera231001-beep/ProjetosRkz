from itertools import combinations
import os
from typing import List, Dict, Any

try:
    import openai
except Exception:
    openai = None


def _implied_prob_from_odds(odds: float) -> float:
    try:
        return 1.0 / float(odds)
    except Exception:
        return 0.0


def simple_scoring(item: Dict[str, Any]) -> Dict[str, Any]:
    # Expect item to contain keys like 'win_rate' (0-100 or 0-1) and 'market_odds'
    # This function now supports detecting value in a list of market odds and return candidate legs.
    win_rate = item.get('win_rate')
    odds_list = item.get('markets') or []  # expecting [{'name','odd'}]

    score = 0.0
    reason = []
    legs = []

    # basic model: use win_rate if available to estimate probability for 1X2
    if win_rate is not None:
        wr = float(win_rate)
        if wr > 1:
            wr = wr / 100.0
        est_prob = wr
    else:
        est_prob = None

    # examine markets
    for m in odds_list:
        odd = None
        if isinstance(m, dict):
            odd = m.get('odd') or m.get('market_odds')
        else:
            try:
                odd = float(m)
            except Exception:
                odd = None
        if odd is None:
            continue
        imp = _implied_prob_from_odds(float(odd))
        # if we have est_prob, compute delta
        delta = None
        if est_prob is not None:
            delta = est_prob - imp
        legs.append({'odd': odd, 'delta': delta, 'market': m})

    # attach legs if any positive delta
    value_legs = [l for l in legs if l['delta']
                  is not None and l['delta'] >= 0.05]
    if value_legs:
        score = max((l['delta'] for l in value_legs))
        reason.append(f"value_legs={len(value_legs)}")
    else:
        reason.append("no clear value legs")

    return {"score": score, "reason": '; '.join(reason), 'legs': legs}


def _mean(values):
    try:
        vals = [float(v) for v in values if v is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)
    except Exception:
        return None


def summarize_numeric_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Convert numeric-like fields to floats and compute simple averages where applicable.

    If a field is a list of numbers it returns the mean; if it's a single number returns it as float.
    """
    out: Dict[str, Any] = {}
    for k, v in stats.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
        elif isinstance(v, list):
            mean = _mean(v)
            out[k] = mean
        else:
            # try parse
            try:
                fv = float(v)
                out[k] = fv
            except Exception:
                out[k] = v
    return out


def _norm_name(s: str) -> str:
    import unicodedata
    import re
    if not s:
        return ''
    t = s.strip().lower()
    t = unicodedata.normalize('NFKD', t).encode(
        'ascii', 'ignore').decode('ascii')
    t = re.sub(r"[^a-z0-9 ]+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _extract_goal_stats(stats: Dict[str, Any]) -> float:
    # try to find a numeric stat representing goals for and goals against
    gf = None
    ga = None
    for k, v in stats.items():
        kn = k.lower()
        if 'goal' in kn or 'gol' in kn or 'gols' in kn:
            if 'against' in kn or 'contra' in kn or 'conced' in kn:
                ga = v if isinstance(v, (int, float)) else ga
            elif 'for' in kn or 'favor' in kn or 'f' in kn or 'avg' in kn or 'media' in kn:
                gf = v if isinstance(v, (int, float)) else gf
            else:
                # if we only have one goals metric, assume it's goals per game
                gf = v if isinstance(v, (int, float)) else gf
    # fallback: if not found, try common keys
    if gf is None:
        for key in ['goals_for_avg', 'gfa', 'goals_for']:
            if key in stats and isinstance(stats[key], (int, float)):
                gf = stats[key]
    if ga is None:
        for key in ['goals_against_avg', 'gaa', 'goals_against']:
            if key in stats and isinstance(stats[key], (int, float)):
                ga = stats[key]
    # as a last resort, return difference if possible
    try:
        return float((gf or 0.0) - (ga or 0.0))
    except Exception:
        return 0.0


def compute_match_probabilities(teamA_stats: Dict[str, Any], teamB_stats: Dict[str, Any]) -> Dict[str, float]:
    """Compute simple probabilities for home/draw/away based on multiple statistics.

    Uses weighted combination of goal-difference proxy, corners, and shots to estimate advantage.
    Returns {'home':p_home,'draw':p_draw,'away':p_away}
    """
    try:
        import math
        # goal difference proxy
        sa = _extract_goal_stats(teamA_stats)
        sb = _extract_goal_stats(teamB_stats)
        goal_diff = sa - sb
        # corners diff (if available)

        def _extract_field(stats, candidates):
            for c in candidates:
                if c in stats and isinstance(stats[c], (int, float)):
                    return float(stats[c])
            return 0.0

        corners_a = _extract_field(
            teamA_stats, ['corners', 'corner', 'escanteios', 'escanteio'])
        corners_b = _extract_field(
            teamB_stats, ['corners', 'corner', 'escanteios', 'escanteio'])
        corners_diff = corners_a - corners_b

        shots_a = _extract_field(teamA_stats, [
                                 'shots_on_target', 'shots', 'chutes', 'chutes a gol', 'chutes_no_alvo'])
        shots_b = _extract_field(teamB_stats, [
                                 'shots_on_target', 'shots', 'chutes', 'chutes a gol', 'chutes_no_alvo'])
        shots_diff = shots_a - shots_b

        # weights (tunable)
        g_w = 0.6
        c_w = 0.25
        s_w = 0.15

        score = g_w * goal_diff + c_w * corners_diff + s_w * shots_diff
        # map to probability via logistic
        p_home = 1.0 / (1.0 + math.exp(-score / 2.0))
        p_home = max(0.02, min(0.98, p_home))
        p_draw = 0.12
        p_away = max(0.01, 1.0 - p_home - p_draw)
        return {'home': p_home, 'draw': p_draw, 'away': p_away}
    except Exception:
        return {'home': 0.5, 'draw': 0.15, 'away': 0.35}


def generate_parlays(candidates: List[Dict[str, Any]], target: float = 2.0, max_legs: int = 3, allow_cross_game: bool = True) -> List[Dict[str, Any]]:
    """Generate parlays from candidate legs until odds >= target.

    candidates: list of legs like {'odd':float,'delta':float,'match':str}
    Returns list of parlays sorted by (odd, total_delta) with structure {'legs':[...], 'odd', 'total_delta'}
    """
    out = []
    # try combinations from 1..max_legs
    for r in range(1, max_legs + 1):
        for combo in combinations(candidates, r):
            # if cross-game not allowed, ensure all matches are same
            if not allow_cross_game:
                matches = [c.get('match') for c in combo]
                if len(set(matches)) > 1:
                    continue
            prod = 1.0
            total_delta = 0.0
            valid = True
            for c in combo:
                if c.get('odd') is None:
                    valid = False
                    break
                prod *= float(c['odd'])
                total_delta += (c.get('delta') or 0.0)
            if not valid:
                continue
            if prod >= target:
                out.append({'legs': combo, 'odd': prod,
                           'total_delta': total_delta})
    # sort by total_delta desc then odd asc
    out.sort(key=lambda x: (-x['total_delta'], x['odd']))
    return out


def _poisson_cdf(lambda_v: float, k: int) -> float:
    """Return cumulative P(X <= k) for Poisson(lambda_v)."""
    import math
    s = 0.0
    for i in range(0, k + 1):
        s += (math.exp(-lambda_v) * (lambda_v ** i) / math.factorial(i))
    return s


def _prob_over_line(lambda_v: float, line: float) -> float:
    """Probability that a Poisson(lambda_v) total is > line (e.g., line=2.5 means >=3)."""
    import math
    # for half-lines like 2.5, count threshold = floor(line)
    threshold = int(float(line))
    return max(0.0, 1.0 - _poisson_cdf(lambda_v, threshold))


def _get_expected_total_from_stats(teamA: Dict[str, Any], teamB: Dict[str, Any], candidates: list) -> float:
    """Sum candidate per-game averages from team stats (e.g., goals, corners)"""
    a = 0.0
    b = 0.0
    for c in candidates:
        # try keys directly
        if isinstance(teamA.get(c), (int, float)):
            a = float(teamA.get(c))
            break
        # try normalized forms
        for k in teamA.keys():
            if c in str(k).lower():
                v = teamA.get(k)
                if isinstance(v, (int, float)):
                    a = float(v)
                    break
        if a:
            break
    for c in candidates:
        if isinstance(teamB.get(c), (int, float)):
            b = float(teamB.get(c))
            break
        for k in teamB.keys():
            if c in str(k).lower():
                v = teamB.get(k)
                if isinstance(v, (int, float)):
                    b = float(v)
                    break
        if b:
            break
    return max(0.0, a + b)


def _detect_market_from_context(mkt: Dict[str, Any]) -> Dict[str, Any]:
    """Try to classify a market into types: GOALS_OVER, GOALS_UNDER, CORNERS_OVER, CORNERS_UNDER, 1X2.

    Returns dict {'type':'GOALS_OVER','line':2.5} or None if unknown.
    """
    import re
    txt = ''
    if isinstance(mkt.get('market_type'), str):
        txt += ' ' + mkt.get('market_type')
    if mkt.get('selection'):
        txt += ' ' + str(mkt.get('selection'))
    if mkt.get('name'):
        txt += ' ' + str(mkt.get('name'))
    if mkt.get('context'):
        txt += ' ' + str(mkt.get('context'))
    t = txt.lower()

    # Over/under numeric lines (support comma decimals)
    ou = re.search(
        r"(over|under|mais de|menos de|o/u|total)\s*([0-9]+(?:[\.,][05])?)", t)
    if ou:
        side = ou.group(1)
        line_raw = ou.group(2).replace(',', '.')
        try:
            line = float(line_raw)
        except Exception:
            line = None
        if 'corn' in t or 'escante' in t:
            mtype = 'CORNERS_OVER' if 'over' in side or 'mais' in side else 'CORNERS_UNDER'
            return {'type': mtype, 'line': line}
        else:
            mtype = 'GOALS_OVER' if 'over' in side or 'mais' in side or 'o/u' in side or 'total' in side else 'GOALS_UNDER'
            return {'type': mtype, 'line': line}

    # patterns like 'o/u 2.5' or 'over 2.5' elsewhere
    # fallback: any numeric token near OU keywords
    ou2 = re.search(r"([0-9]+(?:[\.,][05])?)", t)
    if ou2 and ('over' in t or 'under' in t or 'o/u' in t or 'total' in t or 'mais' in t or 'menos' in t):
        try:
            line = float(ou2.group(1).replace(',', '.'))
        except Exception:
            line = None
        if 'corn' in t or 'escante' in t:
            if 'under' in t or 'menos' in t:
                return {'type': 'CORNERS_UNDER', 'line': line}
            return {'type': 'CORNERS_OVER', 'line': line}
        else:
            if 'under' in t or 'menos' in t:
                return {'type': 'GOALS_UNDER', 'line': line}
            return {'type': 'GOALS_OVER', 'line': line}

    # 1X2 detection and selection mapping
    if '1x2' in t or ('1' in t and 'x' in t and '2' in t) or mkt.get('market_type') == '1X2' or any(k in t for k in ['home', 'away', 'draw', 'empate', 'casa', 'visitante']):
        # try to detect specific selection
        sel = mkt.get('selection') or ''
        s = str(sel).lower()
        if 'casa' in s or 'home' in s or s.strip() == '1':
            return {'type': '1X2', 'line': None, 'selection': '1'}
        if 'visitante' in s or 'away' in s or s.strip() == '2':
            return {'type': '1X2', 'line': None, 'selection': '2'}
        if 'empate' in s or 'draw' in s or 'x' == s.strip().lower():
            return {'type': '1X2', 'line': None, 'selection': 'X'}
        return {'type': '1X2', 'line': None}

    return None


def evaluate_markets_for_match(match: Dict[str, Any], team_stats_map: Dict[str, Dict[str, Any]], value_margin: float = 0.05) -> List[Dict[str, Any]]:
    """Evaluate markets for a single match using team stats map.

    Returns list of legs: {'odd', 'delta', 'market', 'bookmaker', 'match'}
    """
    legs = []
    # try to infer home/away team names
    try:
        from rpa_scraper import parse_match_teams_from_match_page
        teams = parse_match_teams_from_match_page(
            match.get('source_url') or match.get('match_url') or '')
    except Exception:
        teams = []

    if len(teams) >= 2:
        home_name = teams[0]
        away_name = teams[1]
    else:
        home_name = None
        away_name = None

    # find stats by normalized name
    def _norm(s):
        from ai_eval import _norm_name as _n
        return _n(s)

    home_stats = None
    away_stats = None
    if home_name:
        home_stats = team_stats_map.get(_norm(home_name))
    if away_name:
        away_stats = team_stats_map.get(_norm(away_name))

    # Fallback: if stats not available from provided map, attempt to fetch from SofaScore team pages via match page
    if (home_stats is None or away_stats is None) and (match.get('source_url') or match.get('match_url')):
        try:
            from rpa_scraper import extract_team_urls_from_match_page, scrape_sofascore_team_stats
            team_urls = extract_team_urls_from_match_page(
                match.get('source_url') or match.get('match_url'))
            # try match by partial name
            for disp, url in team_urls.items():
                nk = _norm(disp)
                if home_stats is None and _norm(home_name) in nk:
                    s = scrape_sofascore_team_stats(url)
                    if s:
                        home_stats = s
                        # update map
                        team_stats_map[_norm(home_name)] = s
                if away_stats is None and _norm(away_name) in nk:
                    s = scrape_sofascore_team_stats(url)
                    if s:
                        away_stats = s
                        team_stats_map[_norm(away_name)] = s
        except Exception:
            pass

    markets = match.get('markets') or []
    for m in markets:
        odd = None
        try:
            odd = float(m.get('odd'))
        except Exception:
            continue
        # detect market
        info = _detect_market_from_context(m)
        if not info:
            # try to use market_type provided by scraper
            if m.get('market_type') == '1X2':
                info = {'type': '1X2', 'line': None}
            else:
                # generic market -> skip
                continue
        est_prob = None
        mtype = info['type']
        line = info.get('line')
        if mtype in ('GOALS_OVER', 'GOALS_UNDER'):
            # sum goals candidates
            lambda_g = _get_expected_total_from_stats(home_stats or {}, away_stats or {}, [
                                                      'goals', 'goals per game', 'gols', 'gols por jogo', 'avg goals'])
            if lambda_g <= 0:
                continue
            p_over = _prob_over_line(lambda_g, line)
            est_prob = p_over if mtype == 'GOALS_OVER' else (1.0 - p_over)
        elif mtype in ('CORNERS_OVER', 'CORNERS_UNDER'):
            lambda_c = _get_expected_total_from_stats(home_stats or {}, away_stats or {}, [
                                                      'corners', 'escanteios', 'escanteio'])
            if lambda_c <= 0:
                continue
            p_over = _prob_over_line(lambda_c, line)
            est_prob = p_over if mtype == 'CORNERS_OVER' else (1.0 - p_over)
        elif mtype == '1X2':
            # compute simple 1X2 prob using available stats
            if home_stats is None or away_stats is None:
                # fallback: nothing
                continue
            probs = compute_match_probabilities(home_stats, away_stats)
            # if market selection indicates '1' or 'X' or '2' in context, try to pick
            sel = m.get('selection') or ''
            if isinstance(sel, str) and '1' in sel and 'x' not in sel and '2' not in sel:
                est_prob = probs['home']
            elif isinstance(sel, str) and ('x' in sel.lower() or 'draw' in sel.lower()):
                est_prob = probs['draw']
            elif isinstance(sel, str) and '2' in sel:
                est_prob = probs['away']
            else:
                # if we can't map selection, skip
                continue
        else:
            continue

        imp_prob = _implied_prob_from_odds(odd)
        delta = est_prob - imp_prob
        if delta >= value_margin:
            legs.append({'odd': odd, 'delta': delta, 'market': f"{mtype}@{line}" if line is not None else mtype,
                        'bookmaker': m.get('bookmaker') or m.get('source_name'), 'match': match.get('source_url')})
    return legs


def evaluate_matches(items: List[Dict[str, Any]], use_openai: bool = False, openai_api_key: str = None, stats_db_path: str = None) -> List[Dict[str, Any]]:
    """Evaluate a list of scraped match/team items and return scored recommendations.

    If OpenAI key provided and `use_openai` True, will attempt a generative evaluation; otherwise uses a simple heuristic.
    """
    results = []
    # Build team stats map for quick lookup (normalized name -> stats dict)
    team_map = {}
    for it in items:
        # heuristics: items scraped from SofaScore teams have 'team_name'
        if it.get('team_name') and (it.get('source_name') and 'team' in it.get('source_name').lower()):
            name = _norm_name(it.get('team_name'))
            team_map[name] = summarize_numeric_stats(it)

    # If a stats DB path provided, try to augment map from stored stats
    if stats_db_path:
        try:
            import stats_db
            import json as _json
            # collect candidate team names from items
            cand_names = set()
            for it in items:
                for k in ('team_name', 'home', 'away', 'home_name', 'away_name'):
                    if it.get(k):
                        cand_names.add(_norm_name(str(it.get(k))))
            for name in cand_names:
                if name in team_map:
                    continue
                try:
                    rec = stats_db.get_team_stats(name, db_path=stats_db_path)
                    if rec:
                        # prefer raw json if present
                        raw = rec.get('raw') if isinstance(rec, dict) else None
                        sdict = None
                        if raw:
                            try:
                                sdict = _json.loads(raw)
                            except Exception:
                                sdict = rec
                        else:
                            sdict = rec
                        team_map[name] = summarize_numeric_stats(sdict)
                except Exception:
                    continue
        except Exception:
            # ignore DB failures and proceed with in-memory stats
            pass

    # For match items with markets, evaluate markets using team stats
    for it in items:
        if not it.get('markets'):
            # skip non-market items (team summary items preserved but not used)
            continue
        # evaluate markets
        value_margin = float(os.getenv('VALUE_MARGIN', '0.05'))
        # attempt to use env or default; runner may pass configured margin later
        legs = evaluate_markets_for_match(
            it, team_map, value_margin=value_margin)
        # prepare result entry summarizing match and legs
        score = 0.0
        reason = 'no clear value legs'
        if legs:
            score = max(l['delta'] for l in legs)
            reason = f"value_legs={len(legs)}"
        out = {**it, 'score': score, 'reason': reason, 'legs': legs}
        results.append(out)

    # if OpenAI requested, optionally use it as additional summary (not implemented for now)
    if use_openai and openai and openai_api_key:
        # optional: enrich via OpenAI but skip for now
        pass

    return results
