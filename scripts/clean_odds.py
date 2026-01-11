"""Limpa um JSON de odds extraído usando `sanitize_markets` e salva a saída limpa.

Uso:
  python scripts/clean_odds.py --input data/paulistao_odds_new.json \
    --output data/paulistao_odds_clean.json

As mensagens e instruções foram traduzidas para Português (pt-BR).
"""
from rpa_scraper import sanitize_markets
import os
import sys
import time
import json
import argparse

# Garante que a raiz do projeto esteja no caminho antes de importar módulos locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Limpa um arquivo de odds JSON')
    parser.add_argument('--in', '--input', dest='infile',
                        default='data/paulistao_odds_new.json',
                        help='Caminho do arquivo de entrada (JSON)')
    parser.add_argument('--out', '--output', dest='outfile',
                        default='data/paulistao_odds_clean.json',
                        help='Caminho do arquivo de saída (JSON)')
    parser.add_argument('--profile', action='store_true',
                        help='Imprime estatísticas rápidas de execução')
    args = parser.parse_args(argv)

    with open(args.infile, 'r', encoding='utf-8') as f:
        src = json.load(f)

    out = {'generated_at': src.get('generated_at'), 'matches': []}
    start = time.time()
    kept = 0
    removed = 0

    for m in src.get('matches', []):
        mm = {
            'url': m.get('url'),
            'home': m.get('home'),
            'away': m.get('away'),
            'markets': [],
        }
        cleaned = sanitize_markets(m.get('markets', []))
        kept += len(cleaned)
        removed += max(0, len(m.get('markets', [])) - len(cleaned))
        mm['markets'] = cleaned
        out['matches'].append(mm)

    try:
        os.makedirs(os.path.dirname(args.outfile), exist_ok=True)
        with open(args.outfile, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print('Arquivo salvo em:', args.outfile)
    except Exception as e:
        print('Erro ao salvar o arquivo limpo:', e)

    if args.profile:
        print('Markets mantidos:', kept, 'Markets removidos:', removed,
              'Tempo (s):', round(time.time() - start, 2))


if __name__ == '__main__':
    main()
