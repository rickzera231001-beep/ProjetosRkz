"""Analisar odds extraídas + estatísticas do SofaScore para detectar pernas com valor.
Uso: python scripts/analyze_matches.py --odds data/paulistao_odds.json [--save-db] [--use-openai]

Funcionalidades:
- Mensagens em Português
- Contagem de quantas odds/markets foram analisadas
- Suporte opcional a OpenAI para justificar cada perna (config.openai.use_openai ou --use-openai)
- Opção de salvar resultados em SQLite (--save-db)
"""
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import yaml
import argparse
import json
# Carregamento dinâmico para garantir import mesmo em ambientes variados
import importlib.util


def _import_repo_module(name, relpath):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    path = os.path.join(repo_root, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


_ai_eval = _import_repo_module('ai_eval', 'ai_eval.py')
_rpa_scraper = _import_repo_module('rpa_scraper', 'rpa_scraper.py')
evaluate_markets_for_match = getattr(_ai_eval, 'evaluate_markets_for_match')
extract_team_urls_from_match_page = getattr(
    _rpa_scraper, 'extract_team_urls_from_match_page')
scrape_sofascore_team_stats = getattr(
    _rpa_scraper, 'scrape_sofascore_team_stats')
# garantir importações do diretório do projeto (suporte a execução a partir de pasta pai)
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')))


parser = argparse.ArgumentParser()
parser.add_argument('--odds', help='Arquivo JSON com odds',
                    default='data/paulistao_odds.json')
parser.add_argument('--out', help='Arquivo de saída (JSON)',
                    default='data/paulistao_analysis.json')
parser.add_argument('--save-db', action='store_true',
                    help='Salvar resultados em SQLite (data/analysis.db)')
parser.add_argument('--use-openai', action='store_true',
                    help='Forçar uso de OpenAI para justificativas (se configurado)')
args = parser.parse_args()

if not os.path.exists(args.odds):
    raise SystemExit('Arquivo de odds não encontrado: ' + args.odds)

with open(args.odds, 'r', encoding='utf-8') as fh:
    odds_doc = json.load(fh)

# carregar configurações
cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config.local.yaml')
with open(cfg_path, 'r', encoding='utf-8') as fh:
    cfg = yaml.safe_load(fh)

value_margin = float(cfg.get('value_detection', {}).get('value_margin', 0.03))
use_openai_cfg = bool(cfg.get('openai', {}).get('use_openai', False))
openai_key = cfg.get('openai', {}).get(
    'api_key') or os.environ.get('OPENAI_API_KEY')
use_openai = args.use_openai or use_openai_cfg
if use_openai and not openai_key:
    print('Aviso: OpenAI foi solicitada, mas API key não foi encontrada. Desabilitando OpenAI.')
    use_openai = False

if use_openai:
    try:
        import openai
        openai.api_key = openai_key
    except Exception:
        print('Erro ao importar openai; desabilitando OpenAI.')
        use_openai = False

# SQLite helper
DB_PATH = os.path.join('data', 'analysis.db')


def ensure_db():
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 url TEXT,
                 home TEXT,
                 away TEXT,
                 generated_at TEXT
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS legs (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 match_id INTEGER,
                 market TEXT,
                 selection TEXT,
                 odd REAL,
                 implied_prob REAL,
                 est_prob REAL,
                 delta REAL,
                 bookmaker TEXT,
                 comment TEXT,
                 created_at TEXT
                 )''')
    conn.commit()
    return conn

# função auxiliar para obter justificativa via OpenAI (em PT-BR)


def openai_justify(leg, match, team_map):
    prompt = f"""Analise resumida em português (2-3 frases):
Partida: {match.get('home')} x {match.get('away')}
Mercado: {leg.get('market')}
Seleção: {leg.get('selection')}
Odd: {leg.get('odd')}
Probabilidade estimada: {round(leg.get('prob_est', 0), 3)}
Probabilidade implícita: {round(leg.get('implied_prob', 0), 3)}
Delta (valor): {round(leg.get('delta', 0), 3)}
Estatísticas relevantes (quando disponíveis): {team_map}
Explique brevemente por que esta perna tem (ou não) valor e apresente em porcentagem a confiança estimada (ex: ~60%)."""
    try:
        resp = openai.ChatCompletion.create(
            model=cfg.get('openai', {}).get('model', 'gpt-4o-mini'),
            messages=[{"role": "system", "content": "Você é um analista de apostas esportivas que responde em Português de forma breve e objetiva."},
                      {"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        txt = resp['choices'][0]['message']['content'].strip()
        return txt
    except Exception as e:
        return f'Erro ao obter justificativa: {e}'


# análise paralela por partida
results = {'generated_at': __import__(
    'datetime').datetime.utcnow().isoformat(), 'results': []}

print(
    f"Iniciando análise de {len(odds_doc.get('matches', []))} partidas selecionadas...")

# counters
total_markets = 0
total_legs = 0

# prepare DB if requested
conn = None
if args.save_db:
    conn = ensure_db()


def analyze_single(m):
    url = m.get('url')
    home = m.get('home')
    away = m.get('away')
    print(f"\nAnalisando: {home} x {away} - {url}")
    markets = m.get('markets', [])
    print(f"  Markets encontrados: {len(markets)}")

    # Filtrar markets relevantes (gols / escanteios) para economizar processamento
    kws = ['goal', 'gol', 'goals', 'total', 'over',
           'under', 'escante', 'corner', 'corners', 'ou']

    def is_relevant(mk: dict) -> bool:
        txt = ''
        if mk.get('market_type'):
            txt += str(mk.get('market_type')) + ' '
        if mk.get('selection'):
            txt += str(mk.get('selection')) + ' '
        if mk.get('context'):
            txt += str(mk.get('context')) + ' '
        txt = txt.lower()
        return any(k in txt for k in kws)

    filtered = [mk for mk in markets if is_relevant(mk)]
    print(f"  Markets relevantes após filtro: {len(filtered)}")
    if not filtered:
        return {'url': url, 'home': home, 'away': away, 'markets_analyzed': len(markets), 'legs': []}

    # coletar estatísticas por time (usando SofaScore) com cache e paralelo
    team_map = {}
    try:
        team_urls = extract_team_urls_from_match_page(url) or {}
    except Exception:
        team_urls = {}

    # cache global por execução
    if 'team_stats_cache' not in globals():
        globals()['team_stats_cache'] = {}

    # fetch team stats in parallel (max 4 workers)
    to_fetch = []
    for disp, turl in team_urls.items():
        if turl in globals()['team_stats_cache']:
            team_map[disp.strip().lower()] = globals()[
                'team_stats_cache'][turl]
        else:
            to_fetch.append((disp, turl))

    if to_fetch:
        def fetch_team(disp_turl):
            disp, turl = disp_turl
            try:
                s = scrape_sofascore_team_stats(turl)
                return disp.strip().lower(), turl, s
            except Exception:
                return disp.strip().lower(), turl, None

        with ThreadPoolExecutor(max_workers=min(4, len(to_fetch))) as tex:
            futures = [tex.submit(fetch_team, tt) for tt in to_fetch]
            for fut in as_completed(futures):
                try:
                    nk, turl, s = fut.result()
                except Exception:
                    continue
                if s:
                    team_map[nk] = s
                    globals()['team_stats_cache'][turl] = s

    match_obj = {'source_url': url, 'markets': filtered}
    legs = evaluate_markets_for_match(
        match_obj, team_map, value_margin=value_margin)

    # keep goals/corners only (safety)
    legs = [l for l in legs if ('GOALS' in l.get(
        'market') or 'CORNERS' in l.get('market'))]

    # opcional: pedir justificativas para cada leg ao OpenAI (limitado: max 3 por partida)
    if use_openai and legs:
        for l in legs[:3]:
            l['comment'] = openai_justify(
                l, {'home': home, 'away': away}, team_map)

    print(f"  Pernas com valor encontradas: {len(legs)}")
    return {'url': url, 'home': home, 'away': away, 'markets_analyzed': len(filtered), 'legs': legs}


# run concurrently (limit 6 workers)
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = [ex.submit(analyze_single, m)
               for m in odds_doc.get('matches', [])]
    for fut in as_completed(futures):
        try:
            out = fut.result()
        except Exception as e:
            print('Erro em análise de partida:', e)
            continue
        results['results'].append(out)
        total_markets += out.get('markets_analyzed', 0)
        total_legs += len(out.get('legs', []))

# salvar JSON
os.makedirs(os.path.dirname(args.out), exist_ok=True)
with open(args.out, 'w', encoding='utf-8') as fh:
    json.dump(results, fh, ensure_ascii=False, indent=2)

# salvar em DB, se solicitado
if args.save_db and conn:
    c = conn.cursor()
    for r in results['results']:
        c.execute('INSERT INTO matches (url, home, away, generated_at) VALUES (?,?,?,?)',
                  (r['url'], r['home'], r['away'], results['generated_at']))
        match_id = c.lastrowid
        for l in r.get('legs', []):
            c.execute('INSERT INTO legs (match_id, market, selection, odd, implied_prob, est_prob, delta, bookmaker, comment, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)', (
                match_id, l.get('market'), str(l.get('selection')), float(l.get('odd') or 0), float(l.get('implied_prob') or 0), float(
                    l.get('prob_est') or 0), float(l.get('delta') or 0), l.get('bookmaker'), l.get('comment'), results['generated_at']
            ))
    conn.commit()
    conn.close()
    print('\nResultados salvos em SQLite:', DB_PATH)

# resumo final
print('\n---')
print(
    f'Análise concluída: partidas processadas = {len(results["results"])}, markets analisados = {total_markets}, pernas de valor = {total_legs}')
print(f'Relatório salvo em: {args.out}')

print('\nExemplo (primeira partida):')
if results['results']:
    first = results['results'][0]
    print(f" {first['home']} x {first['away']} - markets analisados: {first['markets_analyzed']}, pernas: {len(first['legs'])}")
    for leg in first['legs']:
        print('  -', leg.get('market'), '| odd=', leg.get('odd'), '| delta=',
              round(leg.get('delta', 0), 3), '| bookie=', leg.get('bookmaker'))

print('\nPróximo passo sugerido: avaliar acurácia historicamente salvando resultados (win/lose) e gerar métricas de precisão.')
