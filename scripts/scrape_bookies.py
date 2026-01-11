from rpa_scraper import scrape_betano_odds, scrape_superbet_odds

betano = 'https://www.betano.bet.br/odds/corinthians-ponte-preta/78848213/'
super = 'https://superbet.bet.br/odds/futebol/corinthians-x-ponte-preta-11557139/?t=offer-prematch-20934&mdt=o'

print('Scraping Betano...')
b = scrape_betano_odds(betano)
print('Markets:', len(b.get('markets', [])))
for i, m in enumerate(b.get('markets', [])):
    if i < 20:
        print(i+1, m)

print('\nScraping Superbet...')
s = scrape_superbet_odds(super)
print('Markets:', len(s.get('markets', [])))
for i, m in enumerate(s.get('markets', [])):
    if i < 20:
        print(i+1, m)
