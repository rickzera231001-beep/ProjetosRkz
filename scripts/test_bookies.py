from rpa_scraper import scrape_betano_odds, scrape_superbet_odds
import json
import sys
sys.path.insert(0, '.')

urls = {
    'betano': 'https://www.betano.bet.br/odds/corinthians-ponte-preta/78848213/',
    'superbet': 'https://superbet.bet.br/odds/futebol/corinthians-x-ponte-preta-11557139/?t=offer-prematch-20934&mdt=o'
}


def pretty_print(name, data):
    markets = data.get('markets') or []
    print(f"--- {name} : {len(markets)} markets ---")
    for i, m in enumerate(markets[:10]):
        print(i+1, {k: v for k, v in m.items()
              if k in ('market_type', 'selection', 'odd', 'bookmaker')})


if __name__ == '__main__':
    try:
        b = scrape_betano_odds(urls['betano'])
        pretty_print('Betano', b)
    except Exception as e:
        print('Betano error:', e)
    try:
        s = scrape_superbet_odds(urls['superbet'])
        pretty_print('Superbet', s)
    except Exception as e:
        print('Superbet error:', e)
