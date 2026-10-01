#!/usr/bin/env python3
"""Run native calibre/Qt checks with isolated config and a temporary library."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import runpy

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--calibre-debug', default=shutil.which('calibre-debug') or '/Applications/calibre.app/Contents/MacOS/calibre-debug')
parser.add_argument('--language', choices=('it', 'en'), default='it')
args = parser.parse_args()
brand = runpy.run_path(str(root / 'plugin/branding.py'))
package = root / 'dist' / (brand['NAME'].replace(' ', '') + '-' + '.'.join(map(str, brand['VERSION'])) + '.zip')
with tempfile.TemporaryDirectory(prefix='jev-calibre-test-') as temp:
    env = os.environ.copy()
    env.update({'CALIBRE_CONFIG_DIRECTORY': temp + '/config', 'QT_QPA_PLATFORM': 'offscreen',
                'CALIBRE_OVERRIDE_LANG': args.language, 'JEV_TEST_DIR': temp})
    env.pop('TYPESAFE_API_KEY', None)
    customize = str(Path(args.calibre_debug).with_name(Path(args.calibre_debug).name.replace('calibre-debug', 'calibre-customize')))
    subprocess.run([customize, '-a', str(package)],
                   cwd=root, env=env, check=True, timeout=30)
    subprocess.run([args.calibre_debug, '-e', str(root / 'tests/calibre_smoke.py')],
                   cwd=root, env=env, check=True, timeout=90)
