"""Retrieve source descriptions without modifying original EPUB files."""
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import escape
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
def retrieve(book):
    url = book['page']
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            page = response.read().decode('utf-8')
        match = re.search(r'<div class="summary-text-container">(.*?)</div>', page, re.S)
        if not match: return book['file'], None
        parser = Text(); parser.feed(match.group(1))
        text = ' '.join(' '.join(parser.parts).split())
        return book['file'], '<p>' + escape(text) + '</p><p>Source: <a href="' + url + '">Project Gutenberg</a></p>'
    except Exception:
        return book['file'], None
books = json.loads((ROOT / 'demo/manifest.json').read_text())['books']
with ThreadPoolExecutor(max_workers=3) as pool:
    descriptions = dict(pool.map(retrieve, books))
(ROOT / 'demo/gutenberg-descriptions.json').write_text(json.dumps(descriptions, indent=2))
print('Retrieved descriptions:', sum(bool(x) for x in descriptions.values()))
