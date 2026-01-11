from ai_eval import _norm_name
from bs4 import BeautifulSoup
from rpa_scraper import fetch_html, extract_team_urls_from_sofascore_league, parse_match_teams_from_match_page, scrape_betano_odds, scrape_superbet_odds, scrape_stats
from ai_eval import evaluate_markets_for_match, summarize_numeric_stats

sofa_url = 'https://www.sofascore.com/pt/football/match/ponte-preta-corinthians/hOsuO#id:15176506'
betano = 'https://www.betano.bet.br/odds/corinthians-ponte-preta/78848213/'
super = 'https://superbet.bet.br/odds/futebol/corinthians-x-ponte-preta-11557139/?t=offer-prematch-20934&mdt=o'

# parse team names
teams = parse_match_teams_from_match_page(sofa_url)
print('parsed teams:', teams)
if not teams:
    teams = ['Corinthians', 'Ponte Preta']
home, away = teams[0], teams[1]

# find team page links on the league page (Paulistao) to get team URLs
# Try to find team URLs by scanning the match page for '/team/' links
html = fetch_html(sofa_url)
soup = BeautifulSoup(html, 'html.parser')
team_urls = {}
for a in soup.find_all('a', href=True):
    href = a['href']
    txt = a.get_text(strip=True)
    if '/team/' in href and (home.lower() in txt.lower() or away.lower() in txt.lower()):
        if href.startswith('/'):
            full = 'https://www.sofascore.com' + href
        elif href.startswith('http'):
            full = href
        else:
            full = 'https://www.sofascore.com/' + href
        team_urls[txt.strip()] = full

print('Found team URLs nearby:', team_urls)

# scrape stats for teams using scrape_stats (no selectors; will return title at least)
team_map = {}
for name in [home, away]:
    url = None
    for k, v in team_urls.items():
        if name.lower() in k.lower():
            url = v
            break
    if url:
        try:
            s = scrape_stats(url, {})
            print('Stats for', name, '-> keys:', list(s.keys())[:10])
            team_map[name.lower()] = summarize_numeric_stats(s)
        except Exception as e:
            print('Error scraping team page', url, e)
    else:
        print('No team page found for', name)

# fetch markets from bookmakers
print('\nFetching Betano markets...')
bm_b = scrape_betano_odds(betano)
print('Betano markets:', len(bm_b.get('markets', [])))
print('\nFetching Superbet markets...')
bm_s = scrape_superbet_odds(super)
print('Superbet markets:', len(bm_s.get('markets', [])))

# Build match object expected by evaluate_markets_for_match
match = {'source_url': sofa_url, 'markets': bm_s.get(
    'markets', []) + bm_b.get('markets', [])}

# Prepare team stats map in normalized form
norm_map = {}
for k, v in team_map.items():
    norm_map[_norm_name(k)] = v

legs = evaluate_markets_for_match(match, norm_map, value_margin=0.03)
print('\nDetected legs:', len(legs))
for l in legs:
    print(l)
