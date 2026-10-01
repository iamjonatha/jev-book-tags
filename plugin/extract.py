"""Bounded EPUB extraction in reading order, without modifying source files."""
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import unquote, urlsplit

from .core import clean_text

MAX_MEMBER = 4_000_000


def read_member(archive, name):
    entry = archive.getinfo(name)
    if entry.file_size > MAX_MEMBER:
        raise ValueError('EPUB member exceeds extraction size limit')
    return archive.read(entry)


def resolve(base, href):
    url = urlsplit(href)
    if url.scheme or url.netloc:
        raise ValueError('External EPUB resource')
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(url.path)))
    if path.startswith('../') or path.startswith('/'):
        raise ValueError('Invalid EPUB path')
    return path


def extract_epub(source, max_chars=16000):
    with zipfile.ZipFile(source) as archive:
        container = ET.fromstring(read_member(archive, 'META-INF/container.xml'))
        rootfile = next((e for e in container.iter() if e.tag.endswith('}rootfile')), None)
        if rootfile is None:
            raise ValueError('EPUB package not found')
        package_path = rootfile.attrib['full-path']
        package = ET.fromstring(read_member(archive, package_path))
        items = {e.attrib['id']: e.attrib for e in package.iter() if e.tag.endswith('}item')}
        spine = [e.attrib['idref'] for e in package.iter()
                 if e.tag.endswith('}itemref') and e.attrib.get('linear', 'yes') != 'no']
        toc = ''
        for item in items.values():
            if 'nav' in item.get('properties', '').split():
                html = read_member(archive, resolve(package_path, item['href']))
                toc = clean_text(html.decode('utf-8', 'replace'))[:min(3000, max_chars // 4)]
                break
        if not toc:
            for item in items.values():
                if item.get('media-type') == 'application/x-dtbncx+xml':
                    ncx = ET.fromstring(read_member(archive, resolve(package_path, item['href'])))
                    toc = ' | '.join((e.text or '').strip() for e in ncx.iter()
                                     if e.tag.endswith('}text'))[:min(3000, max_chars // 4)]
                    break
        content = []
        for ident in spine:
            item = items.get(ident, {})
            if item.get('media-type') in ('application/xhtml+xml', 'text/html'):
                if 'nav' not in item.get('properties', '').split():
                    content.append(resolve(package_path, item['href']))
        # Uniform spine sampling; filter short front matter, and deduplicate text.
        count = min(8, len(content))
        indices = sorted({round(i * (len(content) - 1) / max(1, count - 1)) for i in range(count)})
        excerpts, seen = [], set()
        budget = max_chars - len(toc)
        per_doc = max(1, budget // max(1, len(indices)))
        for index in indices:
            text = clean_text(read_member(archive, content[index]).decode('utf-8', 'replace'))
            if len(text) < 200 or text in seen:
                continue
            seen.add(text)
            # Sample beginning and midpoint so a single large chapter is not just truncated.
            if len(text) > per_doc:
                half = per_doc // 2
                text = text[:half] + ' … ' + text[len(text)//2:len(text)//2 + half - 3]
            excerpts.append({'spine_position': index + 1, 'source': content[index], 'text': text[:per_doc]})
        return {'table_of_contents': toc, 'excerpts': excerpts, 'partial': True,
                'source_format': 'EPUB'}
