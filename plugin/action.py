from qt.core import QMenu, QDialog, QVBoxLayout, QDialogButtonBox, QMessageBox, QApplication
from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import gprefs
from calibre.constants import config_dir

from .config import ConfigWidget
from .dialog import CatalogDialog
from .storage import Store
from .settings import library_identity
from .branding import NAME, icon
from .credentials import CredentialError
from .editor import MetadataEditorHook

try:
    load_translations()
except NameError:
    from calibre.utils.localization import _


class SettingsDialog(QDialog):
    def __init__(self, gui):
        super().__init__(gui)
        self.setWindowTitle(NAME + ' — ' + _('Settings'))
        self.setWindowIcon(icon())
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        self.widget = ConfigWidget(gui.current_db.new_api, self, gui=gui)
        layout.addWidget(self.widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        if self.widget.validate():
            try:
                self.widget.save_settings()
            except (CredentialError, ValueError):
                QMessageBox.warning(self, _('API key'), _('Could not save the key. Check its value or disable Remember to use it for this session.'))
                return
            self.accept()


class JevCatalogAction(InterfaceAction):
    name = NAME
    dont_add_to = frozenset({'toolbar-device', 'context-menu-device', 'menubar-device'})
    action_spec = (NAME, None, _('Classify book tags automatically'), None)

    def genesis(self):
        self.dialogs = []
        self.qaction.setIcon(icon())
        self.editor_hook = MetadataEditorHook(self)
        QApplication.instance().installEventFilter(self.editor_hook)
        self.menu = QMenu(self.gui)
        for text, callback in ((_('Classify current book'), lambda: self.run_scope('one')),
                               (_('Classify selected books'), lambda: self.run_scope('selected')),
                               (_('Classify entire library'), lambda: self.run_scope('all')),
                               (_('Settings'), self.configure),
                               (_('Restore last application'), self.restore)):
            action = self.menu.addAction(text)
            action.triggered.connect(callback)
        self.qaction.setMenu(self.menu)
        self.qaction.triggered.connect(lambda: self.run_scope('selected'))

    def initialization_complete(self):
        # Register once; subsequent user removals and ordering stay respected.
        marker = 'jev_book_tags_main_actions_registered'
        if gprefs.get(marker, False):
            return
        changed = False
        for location in ('toolbar', 'context-menu'):
            key = 'action-layout-' + location
            layout = list(gprefs[key])
            if NAME not in layout:
                layout.append(NAME)
                gprefs[key] = tuple(layout)
                changed = True
        if changed:
            self.gui.bars_manager.init_bars()
            self.gui.bars_manager.update_bars()
            self.gui.build_context_menus()
        gprefs[marker] = True

    def run_editor(self, context):
        if any(d.worker and d.worker.isRunning() for d in self.dialogs):
            QMessageBox.information(context.editor, NAME, _('Wait for the current processing job to finish.'))
            return
        for d in self.dialogs:
            d.invalidate()
        try:
            dialog = CatalogDialog(self.gui, [context.editor.book_id], editor=context)
        except Exception:
            QMessageBox.warning(context.editor, NAME, _('Check plugin settings and local journal.'))
            return
        self.dialogs.append(dialog)
        dialog.exec()

    def run_scope(self, scope):
        if any(d.worker and d.worker.isRunning() for d in self.dialogs):
            QMessageBox.information(self.gui, NAME, _('Wait for the current processing job to finish.'))
            return
        view = self.gui.library_view
        if scope == 'all':
            ids = sorted(self.gui.current_db.new_api.all_book_ids())
        elif scope == 'one':
            current = view.currentIndex()
            ids = [view.model().id(current)] if current.isValid() else []
        else:
            ids = [view.model().id(row) for row in view.selectionModel().selectedRows()]
        if not ids:
            QMessageBox.information(self.gui, NAME, _('No books selected.'))
            return
        for d in self.dialogs:
            d.invalidate()
        try:
            dialog = CatalogDialog(self.gui, ids)
        except Exception:
            QMessageBox.warning(self.gui, NAME, _('Check plugin settings and local journal.'))
            return
        self.dialogs.append(dialog)
        dialog.show()

    def configure(self):
        if any(d.worker and d.worker.isRunning() for d in self.dialogs):
            QMessageBox.information(self.gui, NAME, _('Wait for the current processing job to finish.'))
            return
        for dialog in self.dialogs:
            dialog.invalidate()
        SettingsDialog(self.gui).exec()

    def library_changed(self, db):
        for dialog in self.dialogs:
            dialog.invalidate()

    def apply_settings(self):
        for dialog in self.dialogs:
            dialog.invalidate()

    def location_selected(self, loc):
        self.qaction.setEnabled(loc == 'library')

    def shutting_down(self):
        QApplication.instance().removeEventFilter(self.editor_hook)
        for dialog in self.dialogs:
            if dialog.worker and dialog.worker.isRunning():
                dialog.worker.cancel.set()
                dialog.worker.wait(20000)

    def restore(self):
        if any(d.worker and d.worker.isRunning() for d in self.dialogs):
            QMessageBox.information(self.gui, NAME, _('Wait for the current processing job to finish.'))
            return
        for dialog in self.dialogs:
            dialog.invalidate()
        try:
            store = Store(config_dir + '/plugins/jev_catalog_data', library_identity(self.gui.current_db))
            db = self.gui.current_db.new_api
            candidates = [e for e in store.data['journal'] if e['state'] in ('pending', 'applied', 'editor_pending')]
            if not candidates:
                QMessageBox.information(self.gui, _('Restore'), _('No changes to restore.'))
                return
            batch = candidates[-1]['batch']
            entries = [e for e in candidates if e['batch'] == batch]
            if QMessageBox.question(self.gui, _('Restore'), _('Restore the last application? Books edited afterwards will be skipped.')) != QMessageBox.StandardButton.Yes:
                return
            restored, skipped = [], 0
            for entry in reversed(entries):
                book_id, field = entry['book_id'], entry['field']
                if not db.has_id(book_id):
                    skipped += 1
                    continue
                current = list(db.field_for(field, book_id) or [])
                canonical = lambda tags: sorted(t.casefold() for t in tags)
                if canonical(current) == canonical(entry['before']):
                    entry['state'] = 'restored'
                elif canonical(current) == canonical(entry['after']):
                    db.set_field(field, {book_id: entry['before']}, allow_case_change=False)
                    entry['state'] = 'restored'
                    restored.append(book_id)
                else:
                    skipped += 1
                store.save()
            if restored:
                self.gui.library_view.model().refresh_ids(restored)
                self.gui.tags_view.recount()
            QMessageBox.information(self.gui, _('Restore'), _('Restored {count} books; skipped {skipped} conflicts.').format(count=len(restored), skipped=skipped))
        except Exception:
            QMessageBox.warning(self.gui, _('Restore'), _('Could not restore changes. Preserve the journal for inspection.'))
