from rpa_playwright import fetch_html_playwright

url = 'https://r10score.com/match/f74985ea-07eb-54b2-98ac-b58829199b7f/overview'
print('Fetching (wait for table)...')
html = fetch_html_playwright(url, wait_for='table', timeout=20000)
print('len html', len(html))
with open('sample_r10_play.html', 'w', encoding='utf-8') as fh:
    fh.write(html)
print('Wrote sample_r10_play.html')
