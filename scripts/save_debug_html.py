from rpa_scraper import fetch_html

urls = {
    'sofa': 'https://www.sofascore.com/pt/football/match/ponte-preta-corinthians/hOsuO#id:15176506',
    'r10': 'https://r10score.com/match/f74985ea-07eb-54b2-98ac-b58829199b7f/overview'
}
for k, u in urls.items():
    try:
        print(f'Fetching {k}...')
        html = fetch_html(u)
        print(f'Fetched length {len(html)}')
        with open(f'sample_{k}.html', 'w', encoding='utf-8') as fh:
            fh.write(html)
        print(f'Wrote sample_{k}.html')
    except Exception as e:
        print(f'Error fetching {u}: {e}')
