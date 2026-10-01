"""Integration checks executed only by calibre-debug, never against a user's library."""
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
import runpy
from unittest.mock import patch

from qt.core import (QApplication, QMainWindow, QTableView, QStandardItemModel,
                     QStandardItem, QAbstractItemView, QItemSelectionModel, QAction,
                     QMessageBox, Qt)
from calibre.customize.ui import load_plugin
from calibre.db.legacy import LibraryDatabase
from calibre.ebooks.metadata.book.base import Metadata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_core import epub_bytes, response

from calibre.gui2 import Application
app = QApplication.instance() or Application([])
brand = runpy.run_path(str(ROOT / 'plugin/branding.py'))
wrapper = load_plugin(str(ROOT / 'dist' / (brand['NAME'].replace(' ', '') + '-' + '.'.join(map(str, brand['VERSION'])) + '.zip')))
from calibre_plugins.jev_catalog.config import ConfigWidget
from calibre_plugins.jev_catalog.dialog import CatalogDialog
from calibre_plugins.jev_catalog.action import JevCatalogAction
from calibre_plugins.jev_catalog import settings
from calibre_plugins.jev_catalog.storage import Store


class Model(QStandardItemModel):
    def __init__(self, ids):
        super().__init__()
        self.ids, self.refreshed = list(ids), []
        for ident in ids:
            self.appendRow(QStandardItem(str(ident)))

    def id(self, index):
        return self.ids[index.row()]

    def refresh_ids(self, ids):
        self.refreshed.extend(ids)


class Tags:
    def __init__(self):
        self.count = 0

    def recount(self):
        self.count += 1


class Gui(QMainWindow):
    def __init__(self, db, ids):
        super().__init__()
        self.current_db = db
        self.library_view = QTableView(self)
        self.library_view.setModel(Model(ids))
        self.library_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tags_view = Tags()


class MockClient:
    def __init__(self, key, cancel):
        self.cancel = cancel

    def evaluate(self, state, questions, model):
        return response(questions)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = LibraryDatabase(os.environ['JEV_TEST_DIR'] + '/library')
        cls.db = cls.library.new_api
        first = Metadata('Scientific History', ['Test Author'])
        first.comments = '<p>' + 'A scientific history and biography. ' * 20 + '</p>'
        first.tags = ['Manual']
        second = Metadata('Unknown title', ['Test Author'])
        added, duplicates = cls.db.add_books([(first, {}), (second, {})])
        cls.ids = sorted(added)
        cls.db.add_format(cls.ids[1], 'EPUB', io.BytesIO(epub_bytes()))
        cls.library.create_custom_column('jev_categories', 'JEV Categories', 'text', True)
        cls.library.close()
        cls.library = LibraryDatabase(os.environ['JEV_TEST_DIR'] + '/library')
        cls.db = cls.library.new_api

    @classmethod
    def tearDownClass(cls):
        cls.library.close()

    def setUp(self):
        self.gui = Gui(self.library, self.ids)
        self.dialogs = []
        self.addCleanup(self.gui.close)

    def create_action(self):
        action = JevCatalogAction(self.gui, None)
        action.qaction = QAction(self.gui)
        action.genesis()
        self.addCleanup(action.shutting_down)
        return action

    def create_editor(self, ident, editor_class=None):
        from calibre.gui2.metadata.single import MetadataSingleDialog
        editor = (editor_class or MetadataSingleDialog)(self.library, self.gui)
        editor.id_list, editor.current_row = [ident], 0
        editor.set_current_callback = None
        editor(ident)
        editor.show()
        app.processEvents()
        self.addCleanup(editor.hide)
        return editor

    def dialog(self, ids=None):
        d = CatalogDialog(self.gui, ids or self.ids)
        self.dialogs.append(d)
        self.addCleanup(d.close)
        return d

    def process(self, dialog):
        settings.SESSION_KEY = 'test-key-never-transmitted'
        with patch('calibre_plugins.jev_catalog.dialog.JevClient', MockClient):
            dialog.start_work()
            deadline = time.monotonic() + 10
            while dialog.worker.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.005)
            self.assertFalse(dialog.worker.isRunning())
            app.processEvents()

    def test_01_zip_plugin_loads_and_native_italian_translation(self):
        self.assertEqual(wrapper.name, 'JEV Book Tags')
        config = ConfigWidget(self.db)
        self.addCleanup(config.close)
        self.assertEqual(config.test.text(), 'Verifica connessione' if os.environ['CALIBRE_OVERRIDE_LANG'] == 'it' else 'Test connection')
        self.assertTrue(config.validate())
        config.save_settings()
        self.assertNotIn('test-key', str(self.db.pref(settings.PREF_NAME)))
        config.resize(900, 700)
        config.show()
        app.processEvents()
        if os.environ['CALIBRE_OVERRIDE_LANG'] == 'it':
            config.grab().save(str(ROOT / 'dist/settings-preview.png'))

    def test_02_worker_preview_apply_preserves_tags_and_cached_resume(self):
        d = self.dialog()
        before = list(self.db.field_for('tags', self.ids[0]))
        self.process(d)
        self.assertEqual(len(d.results), 2)
        self.assertEqual(list(self.db.field_for('tags', self.ids[0])), before)
        self.assertEqual(d.results[0]['source'], 'metadata')
        self.assertEqual(d.results[1]['source'], 'content')
        self.assertTrue(d.apply_row(0))
        self.assertIn('Manual', self.db.field_for('tags', self.ids[0]))
        self.assertIn('History', self.db.field_for('tags', self.ids[0]))
        self.assertEqual(d.store.data['journal'][-1]['state'], 'applied')
        self.process(d)
        self.assertEqual(d.tokens, 0)
        d.show()
        app.processEvents()
        if os.environ['CALIBRE_OVERRIDE_LANG'] == 'it':
            d.grab().save(str(ROOT / 'dist/catalog-preview.png'))

    def test_03_metadata_change_blocks_stale_application(self):
        d = self.dialog([self.ids[0]])
        self.process(d)
        before = list(self.db.field_for('tags', self.ids[0]))
        self.db.set_field('title', {self.ids[0]: 'Changed after classification'})
        self.assertFalse(d.apply_row(0))
        self.assertEqual(list(self.db.field_for('tags', self.ids[0])), before)

    def test_04_library_change_blocks_writes(self):
        d = self.dialog([self.ids[1]])
        self.process(d)
        before = list(self.db.field_for('tags', self.ids[1]))
        d.invalidate()
        self.assertFalse(d.apply_row(0))
        self.assertEqual(list(self.db.field_for('tags', self.ids[1])), before)

    def test_05_action_scopes_and_restore_conflict(self):
        action = self.create_action()
        view = self.gui.library_view
        view.setCurrentIndex(view.model().index(1, 0))
        action.run_scope('one')
        self.assertEqual(action.dialogs[-1].ids, [self.ids[1]])
        view.selectionModel().select(view.model().index(0, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        action.run_scope('selected')
        self.assertEqual(set(action.dialogs[-1].ids), set(self.ids))
        # A filtered view contains only one book; full scope still uses database IDs.
        view.setModel(Model([self.ids[0]]))
        action.run_scope('all')
        self.assertEqual(action.dialogs[-1].ids, self.ids)
        d = action.dialogs[-1]
        self.process(d)
        self.assertTrue(d.apply_row(1))
        self.db.set_field('tags', {self.ids[1]: ['Manual later edit']})
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), patch.object(QMessageBox, 'information'), patch.object(QMessageBox, 'warning') as warning:
            action.restore()
            warning.assert_not_called()
        self.assertEqual(list(self.db.field_for('tags', self.ids[1])), ['Manual later edit'])
        for dialog in action.dialogs:
            dialog.close()

    def test_06_tags_and_successful_restore(self):
        self.db.set_field('tags', {self.ids[1]: ['Manual restore']})
        d = self.dialog([self.ids[1]])
        self.process(d)
        self.assertTrue(d.apply_row(0))
        self.assertIn('History', self.db.field_for('tags', self.ids[1]))
        action = self.create_action()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), patch.object(QMessageBox, 'information'), patch.object(QMessageBox, 'warning') as warning:
            action.restore()
            warning.assert_not_called()
        self.assertEqual(list(self.db.field_for('tags', self.ids[1])), ['Manual restore'])

    def test_07_autoapply_and_csv_export(self):
        d = self.dialog([self.ids[1]])
        d.auto.setChecked(True)
        self.process(d)
        self.assertIn('History', self.db.field_for('tags', self.ids[1]))
        self.assertTrue(d.results[0]['applied'])
        path = os.environ['JEV_TEST_DIR'] + '/results.csv'
        with patch('calibre_plugins.jev_catalog.dialog.QFileDialog.getSaveFileName', return_value=(path, '')):
            d.export_results()
        text = Path(path).read_text(encoding='utf-8-sig')
        self.assertIn('evidence_probability', text)
        self.assertIn('jev-test', text)
        self.assertNotIn('test-key', text)

    def test_08_cancel_before_first_call(self):
        from calibre_plugins.jev_catalog.dialog import CatalogWorker
        worker = CatalogWorker(self.db, self.ids, settings.load_settings(self.db), 'test-key',
                               Store(os.environ['JEV_TEST_DIR'] + '/cancel', 'cancel-library'))
        worker.cancel.set()
        results = []
        worker.result.connect(results.append)
        with patch('calibre_plugins.jev_catalog.dialog.JevClient', MockClient):
            worker.start()
            self.assertTrue(worker.wait(5000))
            app.processEvents()
        self.assertEqual(results, [])

    def test_09_metadata_editor_button_and_cancel_do_not_write(self):
        action = self.create_action()
        editor = self.create_editor(self.ids[1])
        self.assertIsNotNone(editor._jev_tags_button)
        self.assertFalse(editor._jev_tags_button.icon().isNull())
        if os.environ['CALIBRE_OVERRIDE_LANG'] == 'it':
            editor._jev_tags_button.icon().pixmap(128, 128).save(str(ROOT / 'dist/icon-preview.png'))
            editor.grab().save(str(ROOT / 'dist/metadata-editor-preview.png'))
        self.db.set_field('tags', {self.ids[1]: ['Before editor']})
        editor(self.ids[1])
        editor.comments.set_value('<p>' + 'Unsaved meaningful book description. ' * 20 + '</p>')
        d = CatalogDialog(self.gui, [self.ids[1]], editor=editor._jev_tags_context)
        self.addCleanup(d.close)
        self.process(d)
        self.assertIn('Unsaved meaningful', d.results[0]['metadata']['comments'])
        self.assertTrue(d.apply_row(0))
        self.assertIn('History', editor.tags.current_val)
        self.assertEqual(list(self.db.field_for('tags', self.ids[1])), ['Before editor'])
        d.close()
        with patch('calibre.gui2.metadata.single.confirm', return_value=True):
            editor.reject()
        self.assertEqual(list(self.db.field_for('tags', self.ids[1])), ['Before editor'])
        self.assertEqual(d.store.data['journal'][-1]['state'], 'discarded')

    def test_10_metadata_editor_ok_commits_and_can_restore(self):
        action = self.create_action()
        editor = self.create_editor(self.ids[1])
        editor.tags.set_value(['Before editor', 'Unsaved manual tag'])
        d = CatalogDialog(self.gui, [self.ids[1]], editor=editor._jev_tags_context)
        self.addCleanup(d.close)
        self.process(d)
        self.assertTrue(d.apply_row(0))
        d.close()
        editor.accept()
        self.assertIn('History', self.db.field_for('tags', self.ids[1]))
        self.assertEqual(d.store.data['journal'][-1]['state'], 'applied')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), patch.object(QMessageBox, 'information'), patch.object(QMessageBox, 'warning') as warning:
            action.restore()
            warning.assert_not_called()
        self.assertEqual(set(self.db.field_for('tags', self.ids[1])), {'Before editor', 'Unsaved manual tag'})

    def test_11_model_selection_and_single_tag_mode(self):
        config = ConfigWidget(self.db)
        self.addCleanup(config.close)
        self.assertEqual(config.model.currentText(), 'jev-latest')
        config.model.setCurrentText('jev-preview')
        config.tag_mode.setCurrentIndex(config.tag_mode.findData('single'))
        config.save_settings()
        self.assertEqual(settings.load_settings(self.db)['model'], 'jev-preview')
        d = self.dialog([self.ids[1]])
        self.process(d)
        self.assertEqual(len(d.results[0]['tags']), 1)
        d.table.item(0, 3).setData(Qt.ItemDataRole.UserRole, ['History', 'Biography'])
        self.assertFalse(d.apply_row(0))
        values = settings.load_settings(self.db)
        values['tag_mode'] = 'multiple'
        values['model'] = 'jev-latest'
        settings.save_settings(values, self.db)

    def test_12_exported_vocabulary_import_roundtrip(self):
        config = ConfigWidget(self.db)
        self.addCleanup(config.close)
        source = ROOT / 'jev-categories.json'
        expected = json.loads(source.read_text())['categories']
        with patch('calibre_plugins.jev_catalog.config.QFileDialog.getOpenFileName', return_value=(str(source), 'JSON')):
            config.import_categories()
        self.assertEqual(config.categories(), expected)
        target = Path(os.environ['JEV_TEST_DIR']) / 'exported-tags.json'
        with patch('calibre_plugins.jev_catalog.config.QFileDialog.getSaveFileName', return_value=(str(target), 'JSON')):
            config.export_categories()
        self.assertEqual(json.loads(target.read_text())['categories'], expected)
        self.assertGreater(len(expected), 0)

    def test_13_main_actions_registered_once_without_duplicates(self):
        from unittest.mock import Mock
        action = self.create_action()
        self.gui.bars_manager = Mock()
        self.gui.build_context_menus = Mock()
        prefs = {'action-layout-toolbar': ('Edit Metadata',),
                 'action-layout-context-menu': ('Edit Metadata',)}
        with patch('calibre_plugins.jev_catalog.action.gprefs', prefs):
            action.initialization_complete()
            for key in ('action-layout-toolbar', 'action-layout-context-menu'):
                self.assertEqual(prefs[key].count('JEV Book Tags'), 1)
                self.assertIn('Edit Metadata', prefs[key])
            self.gui.bars_manager.init_bars.assert_called_once()
            self.gui.build_context_menus.assert_called_once()
            prefs['action-layout-toolbar'] = ('Edit Metadata',)
            action.initialization_complete()
            self.assertNotIn('JEV Book Tags', prefs['action-layout-toolbar'])
        self.assertEqual(len(action.menu.actions()), 5)

    def test_14_configurable_editor_positions_and_native_layouts(self):
        from calibre.gui2.metadata.single import (MetadataSingleDialog,
            MetadataSingleDialogAlt1, MetadataSingleDialogAlt2)
        action = self.create_action()
        original = settings.load_settings(self.db)
        try:
            for position in ('tags', 'row', 'bottom'):
                config = ConfigWidget(self.db)
                config.editor_position.setCurrentIndex(config.editor_position.findData(position))
                config.save_settings()
                config.close()
                self.assertEqual(settings.load_settings(self.db)['editor_position'], position)
                for editor_class in (MetadataSingleDialog, MetadataSingleDialogAlt1, MetadataSingleDialogAlt2):
                    with self.subTest(position=position, layout=editor_class.__name__):
                        editor = self.create_editor(self.ids[1], editor_class)
                        button = editor._jev_tags_button
                        self.assertEqual(editor._jev_tags_position, position)
                        self.assertTrue(button.isVisible())
                        self.assertFalse(button.icon().isNull())
                        self.assertTrue(button.accessibleName())
                        if position == 'tags':
                            self.assertEqual(button.text(), '')
                            self.assertEqual(button.width(), 32)
                            self.assertEqual(editor._jev_tags_layout.indexOf(editor.tags), 0)
                            self.assertGreater(editor.tags.width(), 60)
                            self.assertNotIn(button, editor.button_box.buttons())
                        elif position == 'row':
                            self.assertEqual(editor.l.indexOf(button), editor.l.count() - 2)
                        else:
                            self.assertIn(button, editor.button_box.buttons())
                        with patch.object(action, 'run_editor') as run:
                            button.click()
                            run.assert_called_once_with(editor._jev_tags_context)
                        if editor_class is MetadataSingleDialog and os.environ['CALIBRE_OVERRIDE_LANG'] == 'it':
                            editor.grab().save(str(ROOT / ('dist/metadata-editor-' + position + '.png')))
                        editor.hide()
        finally:
            settings.save_settings(original, self.db)

    def add_scored(self, dialog, ident, history=.90, biography=.84, evidence=.99, material=True):
        from calibre_plugins.jev_catalog.core import decide
        from calibre_plugins.jev_catalog.dialog import book_metadata
        probabilities = {'cat_' + c['id']: .01 for c in dialog.values['categories'] if c.get('enabled', True)}
        probabilities.update(cat_history=history, cat_biography=biography, evidence=evidence)
        evaluation = {'probabilities': probabilities, 'model': 'jev-test', 'input_tokens': 0}
        result = decide(evaluation, dialog.values, material)
        metadata = book_metadata(self.db, ident)
        result.update(evaluation=evaluation, book_id=ident, title=metadata['title'], metadata=metadata,
                      previous_tags=list(self.db.field_for('tags', ident)), source='metadata', tokens_billed=0)
        dialog.add_result(result)
        return result

    def test_15_single_book_chips_require_confirmation_and_keep_manual_tags(self):
        self.db.set_field('tags', {self.ids[0]: ['Manual detail']})
        d = self.dialog([self.ids[0]])
        result = self.add_scored(d, self.ids[0])
        self.assertTrue(d.single)
        self.assertTrue(d.table.isHidden())
        panel = d.single_panel
        self.assertTrue(panel.buttons['History'].isChecked())
        self.assertFalse(panel.buttons['Biography'].isChecked())
        self.assertFalse(panel.buttons['Fantasy'].isVisible())
        panel.show_all.setChecked(True)
        self.assertFalse(panel.buttons['Fantasy'].isHidden())
        panel.buttons['Biography'].click()
        self.assertEqual(list(self.db.field_for('tags', self.ids[0])), ['Manual detail'])
        self.assertEqual(result['tags'], ['History'])
        panel.confirm_button.click()
        self.assertEqual(set(self.db.field_for('tags', self.ids[0])), {'Manual detail', 'History', 'Biography'})
        self.assertTrue(result['verified'])
        self.assertTrue(result['applied'])
        self.assertFalse(panel.confirm_button.isEnabled())
        self.assertEqual(result['evaluation']['probabilities']['cat_biography'], .84)
        d.show(); app.processEvents(); app.processEvents()
        self.assertGreaterEqual(panel.grid.columnCount(), 2)
        self.assertIn('1%', panel.buttons['Science Fiction'].text())
        if os.environ['CALIBRE_OVERRIDE_LANG'] == 'it':
            d.grab().save(str(ROOT / 'dist/single-book-tags.png'))

    def test_16_filters_and_detail_verification_preserve_hidden_selections(self):
        d = self.dialog()
        first = self.add_scored(d, self.ids[0])
        second = self.add_scored(d, self.ids[1], history=.80, biography=.79)
        d.finished_work()
        d.filter.setCurrentIndex(d.filter.findData('review'))
        self.assertTrue(d.table.isRowHidden(0))
        self.assertFalse(d.table.isRowHidden(1))
        self.assertIn('1', d.selection_label.text())
        details = d.make_details(self.ids[1])
        self.addCleanup(details.close)
        before = list(self.db.field_for('tags', self.ids[1]))
        details.panel.buttons['Biography'].click()
        self.assertEqual(second['chosen_tags'], ['History', 'Biography'])
        details.panel.confirm_button.click()
        self.assertEqual(second['chosen_tags'], ['History'])
        self.assertTrue(second['verified'])
        self.assertEqual(second['status'], 'review')
        self.assertEqual(list(self.db.field_for('tags', self.ids[1])), before)
        self.assertTrue(d.table.isRowHidden(1))
        self.assertEqual(d.table.item(1, 0).checkState(), Qt.CheckState.Checked)
        self.assertIn('2', d.apply.text())
        d.filter.setCurrentIndex(d.filter.findData('all'))
        d.show(); app.processEvents()
        if os.environ['CALIBRE_OVERRIDE_LANG'] == 'it':
            d.grab().save(str(ROOT / 'dist/bulk-book-tags.png'))
        d.filter.setCurrentIndex(d.filter.findData('error'))
        d.apply_checked()
        self.assertTrue(first['applied'] and second['applied'])

    def test_17_single_tag_near_tie_and_exclusive_chip_selection(self):
        original = settings.load_settings(self.db)
        values = dict(original, tag_mode='single')
        settings.save_settings(values, self.db)
        self.addCleanup(settings.save_settings, original, self.db)
        self.db.set_field('tags', {self.ids[0]: ['Manual exclusive']})
        d = self.dialog([self.ids[0]])
        result = self.add_scored(d, self.ids[0], history=.90, biography=.88)
        self.assertEqual(result['reason'], 'near_tie')
        self.assertEqual(d.table.item(0, 0).checkState(), Qt.CheckState.Unchecked)
        panel = d.single_panel
        panel.buttons['Biography'].click()
        self.assertFalse(panel.buttons['History'].isChecked())
        self.assertEqual(panel.chosen_tags(), ['Biography'])
        panel.confirm_button.click()
        self.assertEqual(set(self.db.field_for('tags', self.ids[0])), {'Manual exclusive', 'Biography'})

    def test_18_closing_details_does_not_confirm_and_empty_selection_is_blocked(self):
        d = self.dialog()
        result = self.add_scored(d, self.ids[0], history=.80, biography=.79)
        details = d.make_details(self.ids[0])
        self.addCleanup(details.close)
        details.panel.buttons['Biography'].click()
        details.reject()
        self.assertFalse(result.get('verified', False))
        self.assertEqual(result['chosen_tags'], ['History', 'Biography'])
        details = d.make_details(self.ids[0])
        self.addCleanup(details.close)
        details.panel.buttons['History'].click()
        details.panel.buttons['Biography'].click()
        self.assertFalse(details.panel.confirm_button.isEnabled())
        self.assertFalse(d.confirm_tags(result, []))

    def test_19_settings_change_blocks_open_detail_confirmation(self):
        original = settings.load_settings(self.db)
        d = self.dialog()
        result = self.add_scored(d, self.ids[0])
        details = d.make_details(self.ids[0])
        self.addCleanup(details.close)
        changed = dict(original, threshold=.95)
        settings.save_settings(changed, self.db)
        self.addCleanup(settings.save_settings, original, self.db)
        before = list(self.db.field_for('tags', self.ids[0]))
        self.assertFalse(d.confirm_tags(result, ['History']))
        self.assertTrue(d.invalidated)
        self.assertEqual(list(self.db.field_for('tags', self.ids[0])), before)

    def test_20_insufficient_evidence_is_never_autoapplied(self):
        d = self.dialog()
        d.auto.setChecked(True)
        before = list(self.db.field_for('tags', self.ids[0]))
        result = self.add_scored(d, self.ids[0], evidence=.79)
        self.assertEqual(result['reason'], 'low_evidence')
        self.assertEqual(result['tags'], [])
        self.assertFalse(result.get('applied', False))
        self.assertEqual(list(self.db.field_for('tags', self.ids[0])), before)
        d.filter.setCurrentIndex(d.filter.findData('insufficient'))
        self.assertFalse(d.table.isRowHidden(0))
        d.select_visible_ready()
        self.assertEqual(d.table.item(0, 0).checkState(), Qt.CheckState.Unchecked)

    def test_21_tag_summary_keeps_all_tags_in_selection_and_csv(self):
        d = self.dialog()
        result = self.add_scored(d, self.ids[0])
        tags = ['History', 'Biography', 'Fantasy']
        self.assertTrue(d.confirm_tags(result, tags))
        self.assertEqual(d.table.item(0, 3).data(Qt.ItemDataRole.UserRole), tags)
        self.assertIn('+1', d.table.item(0, 3).text())
        path = os.environ['JEV_TEST_DIR'] + '/chosen.csv'
        with patch('calibre_plugins.jev_catalog.dialog.QFileDialog.getSaveFileName', return_value=(path, '')):
            d.export_results()
        import csv
        with open(path, encoding='utf-8-sig') as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row['proposed_tags'], ', '.join(tags))
        self.assertEqual(row['machine_suggested_tags'], 'History')
        self.assertEqual(row['verified_by_user'], 'True')

    def test_22_developer_mode_and_advanced_options(self):
        old = settings.global_prefs['developer_mode']
        try:
            settings.global_prefs['developer_mode'] = False
            config = ConfigWidget(self.db)
            self.assertFalse(config.developer_mode.isChecked())
            self.assertTrue(config.advanced.isHidden())
            self.assertTrue(config.table.isColumnHidden(3))
            config.advanced_toggle.setChecked(True)
            self.assertFalse(config.advanced.isHidden())
            self.assertFalse(config.table.isColumnHidden(3))
            d = self.dialog([self.ids[0]])
            self.add_scored(d, self.ids[0])
            d.finished_work()
            self.assertTrue(d.single_panel.inspect.isHidden())
            plugin_translate = CatalogDialog.finished_work.__globals__.get('_', lambda text: text)
            self.assertNotIn(plugin_translate('New input tokens: {tokens}.').format(tokens=0), d.status.text())
            settings.global_prefs['developer_mode'] = True
            dev = self.dialog([self.ids[0]])
            self.add_scored(dev, self.ids[0])
            dev.finished_work()
            self.assertFalse(dev.single_panel.inspect.isHidden())
            self.assertIn(plugin_translate('New input tokens: {tokens}.').format(tokens=0), dev.status.text())
        finally:
            settings.global_prefs['developer_mode'] = old


outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeTests))
raise SystemExit(0 if outcome.wasSuccessful() else 1)
