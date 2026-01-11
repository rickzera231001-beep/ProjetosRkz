from rpa_scraper import parse_match_teams_from_match_page, scrape_r10_stats, find_odds_for_match_on_bookmaker

sofa_url = 'https://www.sofascore.com/pt/football/match/ponte-preta-corinthians/hOsuO#id:15176506'
r10_url = 'https://r10score.com/match/f74985ea-07eb-54b2-98ac-b58829199b7f/overview'

print('Parsing teams from SofaScore...')
teams = parse_match_teams_from_match_page(sofa_url)
print('Teams:', teams)

print('\nScraping R10Score match page...')
r10_stats = scrape_r10_stats(r10_url)
print('R10 stats keys:', list(r10_stats.keys())[:40])
for k, v in list(r10_stats.items())[:30]:
    print(f'  {k}: {v}')

match = {'source_url': sofa_url}
if teams:
    match['home_team'] = teams[0]
    match['away_team'] = teams[1]

# try to find odds on Betano and Superbet
bookies = ['https://www.betano.bet.br/', 'https://superbet.bet.br/']
for b in bookies:
    print(f'\nSearching {b} for markets near team names...')
    try:
        found = find_odds_for_match_on_bookmaker(match, b)
        print('Found markets:', len(found.get('markets', [])))
        for m in found.get('markets', [])[:10]:
            print(' ', m)
    except Exception as e:
        print('  Error searching bookmaker:', e)
