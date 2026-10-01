import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('release_tools',Path(__file__).resolve().parents[1]/'scripts/prepare_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('plugin','docs/media','dist'):(self.root/name).mkdir(parents=True)
        (self.root/'plugin/branding.py').write_text("NAME='JEV Book Tags'\nVERSION=(1,1,1)\n")
        self.metadata="class Plugin:\n name='JEV Book Tags'\n version=(1,1,1)\n minimum_calibre_version=(9,0,0)\n"
        (self.root/'plugin/__init__.py').write_text(self.metadata)
        (self.root/'CHANGELOG.md').write_text('## 1.1.1 — 2026-10-01\n\n- A useful change.\n')
        for name in ('DEMO.md','demo.html'):(self.root/'docs'/name).write_text('Public demo')
        with zipfile.ZipFile(self.root/'dist/JEVBookTags-1.1.1.zip','w') as z:z.writestr('__init__.py',self.metadata)
        self.patcher=patch.object(release,'ROOT',self.root);self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_release_assets_preserve_installable_zip_and_checksums(self):
        out=release.prepare('owner/project')
        self.assertEqual((out/'JEVBookTags.zip').read_bytes(),(out/'JEVBookTags-1.1.1.zip').read_bytes())
        for line in (out/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ');self.assertEqual(digest,hashlib.sha256((out/name).read_bytes()).hexdigest())
        self.assertIn('Version History',(out/'MobileRead-post.txt').read_text())
        self.assertIn('No forum post',(out/'MobileRead-handoff.md').read_text())

    def test_mismatching_version_blocks_release(self):
        (self.root/'plugin/__init__.py').write_text(self.metadata.replace('(1,1,1)','(1,1,2)'))
        with self.assertRaises(ValueError):release.prepare('owner/project')

    def test_missing_changelog_blocks_release(self):
        (self.root/'CHANGELOG.md').write_text('## 1.1.0 — 2026-10-01\nOther change\n')
        with self.assertRaises(ValueError):release.prepare('owner/project')

    def test_stale_zip_blocks_release(self):
        (self.root/'plugin/__init__.py').write_text(self.metadata+'\n# changed\n')
        with self.assertRaises(ValueError):release.prepare('owner/project')
