#!/usr/bin/env python3
"""Build a reproducible calibre ZIP and native gettext catalogs."""
import ast
import io
import json
from pathlib import Path
import struct
import zipfile
import runpy

ROOT = Path(__file__).resolve().parents[1]
BRAND = runpy.run_path(str(ROOT / 'plugin/branding.py'))
PACKAGE_NAME = BRAND['NAME'].replace(' ', '') + '-' + '.'.join(map(str, BRAND['VERSION'])) + '.zip'


def messages():
    result = set()
    for path in (ROOT / 'plugin').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_':
                if node.args and isinstance(node.args[0], ast.Constant):
                    result.add(node.args[0].value)
    return sorted(result)


def mo_catalog(mapping):
    pairs = sorted((k.encode(), v.encode()) for k, v in mapping.items())
    count = len(pairs)
    originals = b''.join(k + b'\0' for k, v in pairs)
    translations = b''.join(v + b'\0' for k, v in pairs)
    offset = 28 + count * 16
    orig_table, trans_table, pos = [], [], offset
    for key, _ in pairs:
        orig_table.append(struct.pack('<2I', len(key), pos))
        pos += len(key) + 1
    for _, value in pairs:
        trans_table.append(struct.pack('<2I', len(value), pos))
        pos += len(value) + 1
    return (struct.pack('<7I', 0x950412de, 0, count, 28, 28 + count * 8, 0, 0)
            + b''.join(orig_table) + b''.join(trans_table) + originals + translations)


def build():
    strings = messages()
    translation_dir = ROOT / 'plugin/translations'
    translation_dir.mkdir(exist_ok=True)
    locale_dir = ROOT / 'translations'
    # Any translations/<locale>.json is compiled into the plugin. The JSON map
    # is intentionally the only per-language input required from translators.
    catalogs = {}
    for source in sorted(locale_dir.glob('*.json')):
        language = source.stem
        mapping = json.loads(source.read_text(encoding='utf-8'))
        missing = set(strings) - set(mapping)
        empty = {key for key in set(strings) & set(mapping)
                 if not isinstance(mapping[key], str) or not mapping[key].strip()}
        missing |= empty
        if missing:
            raise ValueError(f'Missing {language} translations: ' + repr(sorted(missing)))
        mapping = {k: mapping[k] for k in strings}
        nplurals = 'nplurals=2; plural=(n != 1);'
        if language.startswith('ru'):
            nplurals = 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);'
        mapping[''] = f'Content-Type: text/plain; charset=UTF-8\nLanguage: {language}\nPlural-Forms: {nplurals}\n'
        catalog = mo_catalog(mapping)
        catalogs[language] = mapping
        (translation_dir / f'{language}.mo').write_bytes(catalog)
        # Confirm each compiled catalog can be loaded by Python gettext.
        import gettext
        gettext.GNUTranslations(io.BytesIO(catalog))

    # Keep the existing Italian gettext source and create the translator template.
    for language, filename in (('it', 'it.po'), ('', 'messages.pot')):
        rows = []
        mapping = catalogs.get(language, {})
        header = mapping.get('', 'Content-Type: text/plain; charset=UTF-8\nLanguage: en\n')
        entries = {'': header}
        entries.update({s: mapping.get(s, '') for s in strings})
        for key, value in entries.items():
            rows.append('msgid ' + json.dumps(key, ensure_ascii=False) + '\nmsgstr ' + json.dumps(value, ensure_ascii=False))
        (locale_dir / filename).write_text('\n\n'.join(rows) + '\n', encoding='utf-8')
    target = ROOT / 'dist' / PACKAGE_NAME
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / 'plugin').rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                info = zipfile.ZipInfo(path.relative_to(ROOT / 'plugin').as_posix(), (2026, 9, 30, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
    print(target)
    print(f'{len(strings)} interface strings translated')


if __name__ == '__main__':
    build()
