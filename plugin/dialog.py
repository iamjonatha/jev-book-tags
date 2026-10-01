import threading
import uuid
import csv
import json

from qt.core import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                     QTableWidget, QTableWidgetItem, Qt, QThread, pyqtSignal,
                     QProgressBar, QCheckBox, QMessageBox, QFileDialog, QPlainTextEdit,
                     QComboBox, QWidget)
from calibre.constants import config_dir

from .client import JevClient, JevError, Cancelled
from .core import metadata_state, merge_tags, validate_settings, fingerprint, questions, ranked_candidates
from .detail import TagChoicePanel, reason_text
from .engine import classify
from .extract import extract_epub
from .storage import Store
from .settings import api_key, load_settings, library_identity, global_prefs
from .branding import NAME, icon

try:
    load_translations()
except NameError:
    from calibre.utils.localization import _


def book_metadata(db, book_id):
    mi = db.get_metadata(book_id)
    return {'title': mi.title, 'authors': mi.authors or [], 'comments': mi.comments or '',
            'languages': mi.languages or [], 'series': mi.series}


class CatalogWorker(QThread):
    result = pyqtSignal(object)
    progress = pyqtSignal(int)

    def __init__(self, db, ids, values, key, store, overrides=None):
        super().__init__()
        self.db, self.ids, self.values = db, ids, values
        self.key, self.store, self.cancel = key, store, threading.Event()
        self.overrides = overrides or {}

    def run(self):
        try:
            client = JevClient(self.key, self.cancel)
        except JevError:
            self.result.emit({'error': 'connection', 'book_id': None, 'title': ''})
            return
        finally:
            self.key = ''
        for count, book_id in enumerate(self.ids, 1):
            if self.cancel.is_set():
                break
            metadata = {'title': str(book_id)}
            try:
                if not self.db.has_id(book_id):
                    raise ValueError('Book removed')
                override = self.overrides.get(book_id)
                metadata = override['metadata'] if override else book_metadata(self.db, book_id)
                formats = self.db.formats(book_id) or ()
                loader = (lambda ident=book_id: self.db.format(ident, 'EPUB', as_file=True)) if 'EPUB' in formats else None
                result = classify(metadata, self.values, client, self.store, loader)
                result.update({'book_id': book_id, 'title': metadata['title'],
                               'metadata': metadata,
                               'previous_tags': override['tags'] if override else list(self.db.field_for(self.values['destination'], book_id) or [])})
            except Cancelled:
                break
            except JevError:
                result = {'book_id': book_id, 'title': metadata['title'], 'error': 'connection'}
                # Stop on authentication/transport errors rather than repeating them for the whole library.
                self.result.emit(result)
                self.progress.emit(count)
                break
            except Exception:
                result = {'book_id': book_id, 'title': metadata['title'], 'error': 'book'}
            self.result.emit(result)
            self.progress.emit(count)


class CatalogDialog(QDialog):
    def __init__(self, gui, ids, editor=None):
        super().__init__(editor.editor if editor else gui)
        self.editor = editor
        self.gui, self.legacy = gui, gui.current_db
        self.db, self.identity = self.legacy.new_api, library_identity(self.legacy)
        self.ids, self.values = list(ids), load_settings(self.db)
        validate_settings(self.values)
        if self.values['destination'] != 'tags':
            field = self.db.field_metadata[self.values['destination']]
            if field['datatype'] != 'text' or not field['is_multiple']:
                raise ValueError('Invalid destination')
        self.store = Store(config_dir + '/plugins/jev_catalog_data', self.identity)
        self.results, self.worker, self.close_requested = [], None, False
        self.invalidated = False
        self.batch = uuid.uuid4().hex
        self.tokens = 0
        self.single = len(self.ids) == 1
        self.single_panel = None
        self.detail_dialogs = []
        self.setWindowTitle(NAME + ' — ' + _('Preview'))
        self.setWindowIcon(icon())
        self.resize(1150, 650)
        layout = QVBoxLayout(self)
        summary = _('Books: {count}. Input: {mode}. Destination: {field}.').format(
            count=len(ids), mode={'auto': _('Automatic'), 'metadata': _('Metadata only'),
                                  'content': _('Metadata and EPUB excerpts')}[self.values['mode']],
            field=self.values['destination'])
        layout.addWidget(QLabel(summary))
        note = QLabel(_('Starting sends book metadata and, when enabled, EPUB excerpts to TypeSafe AI. Existing tags are preserved.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        if editor:
            editor_note = QLabel(_('Suggested tags are added to the metadata form. They are saved only when you confirm that form with OK.'))
            editor_note.setWordWrap(True)
            layout.addWidget(editor_note)
        self.auto = QCheckBox(_('Automatically apply results ready for assignment'))
        if self.single:
            self.auto.setVisible(False)
        layout.addWidget(self.auto)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([_('Apply'), _('Book'), _('Existing tags'), _('Tags to assign'), _('Top confidence'), _('Input'), _('Status'), _('Details')])
        self.table.setColumnHidden(2, True)
        self.table.setColumnHidden(5, True)
        self.table.itemChanged.connect(lambda item: self.update_selection() if item.column() == 0 else None)
        self.table.cellDoubleClicked.connect(lambda row, col: self.open_details(self.results[row].get('book_id')))
        filters = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(self.apply_filter)
        filters.addWidget(QLabel(_('Show'))); filters.addWidget(self.filter)
        self.select_ready = QPushButton(_('Select visible ready books'))
        self.select_ready.clicked.connect(self.select_visible_ready)
        filters.addWidget(self.select_ready)
        self.selection_label = QLabel(); filters.addWidget(self.selection_label, 1)
        self.filter_bar = QWidget(); self.filter_bar.setLayout(filters)
        layout.addWidget(self.filter_bar)
        self.single_host = QWidget(); self.single_layout = QVBoxLayout(self.single_host)
        self.single_layout.setContentsMargins(0, 0, 0, 0)
        self.single_waiting = QLabel(_('Start classification to see suggested tags for this book.'))
        self.single_layout.addWidget(self.single_waiting)
        layout.addWidget(self.single_host, 1)
        self.single_host.setVisible(self.single)
        self.filter_bar.setVisible(not self.single)
        self.table.setVisible(not self.single)
        for col, width in enumerate((55, 260, 160, 280, 165, 90, 175, 95)):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(ids))
        layout.addWidget(self.progress)
        self.status = QLabel(_('Ready. No book has been changed.'))
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.start = QPushButton(_('Start / resume'))
        self.start.clicked.connect(lambda: self.start_work())
        self.retry = QPushButton(_('Retry failed rows'))
        self.retry.clicked.connect(lambda: self.retry_failed())
        self.retry.setEnabled(False)
        self.cancel = QPushButton(_('Cancel processing'))
        self.cancel.clicked.connect(self.cancel_work)
        self.cancel.setEnabled(False)
        self.apply = QPushButton(_('Apply checked rows'))
        self.apply.clicked.connect(self.apply_checked)
        self.apply.setVisible(not self.single)
        self.apply.setEnabled(False)
        self.close_button = QPushButton(_('Close'))
        self.close_button.clicked.connect(self.close)
        self.export = QPushButton(_('Export results (CSV)'))
        self.export.clicked.connect(self.export_results)
        self.export.setEnabled(False)
        for button in (self.start, self.retry, self.cancel, self.apply, self.export, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.update_filters()

    def same_library(self):
        return (not self.invalidated and self.gui.current_db is self.legacy
                and library_identity(self.gui.current_db) == self.identity
                and load_settings(self.db) == self.values
                and (self.editor is None or self.editor.valid(self.ids[0])))

    def invalidate(self):
        self.invalidated = True
        self.cancel_work()
        self.start.setEnabled(False)
        self.apply.setEnabled(False)
        self.export.setEnabled(False)
        if self.single_panel:
            self.single_panel.confirm_button.setEnabled(False)
        for dialog in self.detail_dialogs:
            dialog.reject()
        self.status.setText(_('Preview expired. Reopen the plugin for the current library and settings.'))

    def start_work(self, run_ids=None, reset=True):
        if not self.same_library():
            return self.invalidate()
        if not api_key():
            QMessageBox.warning(self, _('Configuration'), _('Enter an API key in plugin settings first.'))
            return
        if self.worker and self.worker.isRunning():
            return
        run_ids = list(self.ids if run_ids is None else run_ids)
        if reset:
            self.table.setRowCount(0)
            self.results = []
            self.tokens = 0
            self.clear_single()
            self.update_filters()
        self.progress.setValue(0)
        self.progress.setRange(0, len(run_ids))
        self.start.setEnabled(False)
        self.retry.setEnabled(False)
        self.auto.setEnabled(False)
        self.cancel.setEnabled(True)
        self.apply.setEnabled(False)
        self.status.setText(_('Processing. Successful evaluations are cached for resume.'))
        overrides = {self.ids[0]: {'metadata': self.editor.snapshot(), 'tags': self.editor.tags()}} if self.editor else None
        self.worker = CatalogWorker(self.db, run_ids, self.values, api_key(), self.store, overrides)
        self.worker.result.connect(self.add_result)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self.finished_work)
        self.worker.start()

    def retry_failed(self):
        if not self.same_library():
            return self.invalidate()
        if self.worker and self.worker.isRunning():
            return
        failed_ids = [result.get('book_id') for result in self.results
                      if result.get('error') and result.get('book_id') is not None]
        if not failed_ids:
            return
        if not api_key():
            QMessageBox.warning(self, _('Configuration'), _('Enter an API key in plugin settings first.'))
            return
        for row in range(self.table.rowCount() - 1, -1, -1):
            if self.results[row].get('error'):
                self.table.removeRow(row)
                del self.results[row]
        self.start_work(failed_ids, reset=False)

    def cancel_work(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.status.setText(_('Cancelling; waiting for the current request to finish.'))

    def add_result(self, result):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.results.append(result)
        checkbox = QTableWidgetItem()
        checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        ready = result.get('status') == 'ready' and not result.get('error')
        checkbox.setCheckState(Qt.CheckState.Checked if ready else Qt.CheckState.Unchecked)
        if result.get('error'):
            checkbox.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table.setItem(row, 0, checkbox)
        result.setdefault('chosen_tags', list(result.get('tags', [])))
        probabilities = result.get('evaluation', {}).get('probabilities', {})
        ranked = ranked_candidates(result['evaluation'], self.values) if result.get('evaluation') else []
        confidence = format(ranked[0]['probability'], '.0%') if ranked else '—'
        texts = (result['title'], ', '.join(result.get('previous_tags', [])),
                 self.tag_summary(result['chosen_tags']), confidence,
                 _('Metadata + excerpts') if result.get('source') == 'content' else _('Metadata'), self.row_status(result))
        for col, text in enumerate(texts, 1):
            item = QTableWidgetItem(text)
            item.setToolTip(reason_text(result) if col == 6 else text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if col == 3:
                item.setData(Qt.ItemDataRole.UserRole, list(result['chosen_tags']))
                item.setToolTip(', '.join(result['chosen_tags']))
            if col == 4 and ranked:
                item.setToolTip(_('{tag}: {probability:.0%}. This is the highest category score, not overall classification accuracy.').format(tag=ranked[0]['name'], probability=ranked[0]['probability']))
            self.table.setItem(row, col, item)
        detail_button = QPushButton(_('Details…'))
        detail_button.clicked.connect(lambda _checked=False, ident=result.get('book_id'): self.open_details(ident))
        self.table.setCellWidget(row, 7, detail_button)
        self.update_filters()
        if self.single:
            self.show_single(result)
        self.tokens += result.get('tokens_billed', 0)
        if ready and self.auto.isChecked() and self.same_library():
            try:
                self.apply_row(row)
            except Exception:
                self.cancel_work()
                self.table.item(row, 6).setText(_('Could not apply tags. Check the journal before retrying.'))
        self.update_filters()

    def tag_summary(self, tags):
        text = ', '.join(tags[:2])
        return _('{tags} (+{count})').format(tags=text, count=len(tags) - 2) if len(tags) > 2 else text

    def row_status(self, result):
        if result.get('error'):
            return _('Connection error; processing stopped') if result['error'] == 'connection' else _('Book could not be read')
        if result.get('applied'):
            return _('Added to editor; confirm with OK') if self.editor else _('Applied')
        if result.get('verified'):
            return _('Verified by you')
        if not result.get('supported'):
            return _('Insufficient evidence')
        return _('Ready for assignment') if result.get('status') == 'ready' else _('Review required')

    def bucket(self, result):
        if result.get('error'):
            return 'error'
        if result.get('applied'):
            return 'applied'
        if result.get('verified'):
            return 'ready'
        if not result.get('supported'):
            return 'insufficient'
        return 'ready' if result.get('status') == 'ready' else 'review'

    def update_filters(self):
        current = self.filter.currentData() or 'all'
        self.filter.blockSignals(True)
        self.filter.clear()
        for name, label in (('all', _('All')), ('ready', _('Ready / verified')),
                            ('review', _('To review')), ('insufficient', _('Insufficient evidence')),
                            ('error', _('Errors')), ('applied', _('Applied'))):
            count = len(self.results) if name == 'all' else sum(self.bucket(r) == name for r in self.results)
            self.filter.addItem(_('{label} ({count})').format(label=label, count=count), name)
        self.filter.setCurrentIndex(max(0, self.filter.findData(current)))
        self.filter.blockSignals(False)
        self.apply_filter()

    def apply_filter(self, *_):
        selected = self.filter.currentData() or 'all'
        for row, result in enumerate(self.results):
            self.table.setRowHidden(row, selected != 'all' and self.bucket(result) != selected)
        self.update_selection()

    def update_selection(self):
        checked = [row for row in range(self.table.rowCount()) if self.table.item(row, 0)
                   and self.table.item(row, 0).checkState() == Qt.CheckState.Checked]
        hidden = sum(self.table.isRowHidden(row) for row in checked)
        text = _('Selected books: {count} ({hidden} outside the filter)').format(count=len(checked), hidden=hidden)
        self.selection_label.setText(text)
        if hasattr(self, 'apply'):
            self.apply.setText(_('Apply selected books ({count}, {hidden} hidden)').format(count=len(checked), hidden=hidden))

    def select_visible_ready(self):
        for row, result in enumerate(self.results):
            if not self.table.isRowHidden(row) and self.bucket(result) == 'ready':
                self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        self.update_selection()

    def clear_single(self):
        if self.single_panel:
            self.single_layout.removeWidget(self.single_panel)
            self.single_panel.deleteLater()
            self.single_panel = None
        self.single_waiting.show()

    def show_single(self, result):
        self.clear_single()
        self.single_waiting.hide()
        label = _('Add to metadata form') if self.editor else _('Apply tags')
        panel = TagChoicePanel(result, self.values, label, self.single_host)
        panel.inspect_input.connect(lambda: self.view_input(result.get('book_id')))
        panel.confirmed.connect(lambda tags: self.confirm_tags(result, tags, apply=True))
        self.single_layout.addWidget(panel)
        self.single_panel = panel
        self.resize(900, 700)

    def make_details(self, book_id):
        if not self.same_library():
            self.invalidate()
            return None
        result = next((r for r in self.results if r.get('book_id') == book_id), None)
        if result is None:
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle(NAME + ' — ' + _('Book details'))
        dialog.setWindowIcon(icon()); dialog.resize(850, 620)
        layout = QVBoxLayout(dialog)
        panel = TagChoicePanel(result, self.values, _('Confirm tags'), dialog)
        panel.inspect_input.connect(lambda: self.view_input(book_id))
        panel.confirmed.connect(lambda tags: dialog.accept() if self.confirm_tags(result, tags) else None)
        layout.addWidget(panel)
        close = QPushButton(_('Close')); close.clicked.connect(dialog.reject); layout.addWidget(close)
        dialog.panel = panel
        self.detail_dialogs.append(dialog)
        return dialog

    def open_details(self, book_id):
        dialog = self.make_details(book_id)
        if dialog:
            dialog.exec()
            self.detail_dialogs.remove(dialog)
            dialog.deleteLater()

    def confirm_tags(self, result, tags, apply=False):
        if not self.same_library():
            self.invalidate()
            return False
        if result not in self.results or result.get('applied') or result.get('error'):
            return False
        allowed = {c['name'] for c in self.values['categories'] if c.get('enabled', True)}
        if not tags or any(tag not in allowed for tag in tags) or (self.values['tag_mode'] == 'single' and len(tags) != 1):
            return False
        if not self.db.has_id(result['book_id']):
            QMessageBox.information(self, _('Review required'), _('Book removed; skipped'))
            return False
        current = self.editor.snapshot() if self.editor else book_metadata(self.db, result['book_id'])
        if metadata_state(current) != metadata_state(result['metadata']):
            QMessageBox.information(self, _('Review required'), _('Metadata changed; classify again'))
            return False
        row = self.results.index(result)
        result['chosen_tags'], result['verified'] = list(tags), True
        self.table.item(row, 3).setText(self.tag_summary(tags))
        self.table.item(row, 3).setData(Qt.ItemDataRole.UserRole, list(tags))
        self.table.item(row, 3).setToolTip(', '.join(tags))
        self.table.item(row, 6).setText(self.row_status(result))
        self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        if apply:
            try:
                success = self.apply_row(row)
            except Exception:
                QMessageBox.warning(self, _('Apply'), _('Could not apply tags. Check the journal before retrying.'))
                return False
            if success and self.single_panel:
                self.single_panel.confirm_button.setEnabled(False)
                self.single_panel.reason.setText(self.row_status(result))
            self.update_filters()
            return success
        self.update_filters()
        return True

    def view_input(self, book_id):
        if not self.same_library():
            return self.invalidate()
        result = next((item for item in self.results if item.get('book_id') == book_id), None)
        if not result or result.get('error'):
            return
        state = metadata_state(result['metadata'])
        try:
            if result.get('source') == 'content':
                if 'EPUB' not in (self.db.formats(book_id) or ()):
                    raise ValueError('EPUB unavailable')
                with self.db.format(book_id, 'EPUB', as_file=True) as source:
                    state['book'].update(extract_epub(source, self.values['max_chars']))
            if fingerprint(state, self.values) != result.get('input_fingerprint'):
                QMessageBox.information(self, _('Request input'), _('The book data changed after classification. Run it again to inspect the exact input that was sent.'))
                return
        except Exception:
            QMessageBox.information(self, _('Request input'), _('The original input is no longer available. Run classification again to inspect the sent data.'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(_('Request input') + ' — ' + result.get('title', ''))
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        note = QLabel(_('This is the request payload sent to TypeSafe AI. EPUB excerpts are partial samples.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        view = QPlainTextEdit(dialog)
        view.setReadOnly(True)
        payload = {'model': self.values['model'], 'state': state, 'questions': questions(self.values)}
        view.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        layout.addWidget(view)
        close = QPushButton(_('Close'))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def finished_work(self):
        self.start.setEnabled(self.same_library())
        self.retry.setEnabled(self.same_library() and any(
            r.get('error') and r.get('book_id') is not None for r in self.results))
        self.auto.setEnabled(True)
        self.cancel.setEnabled(False)
        self.apply.setEnabled(self.same_library() and bool(self.results))
        self.export.setEnabled(bool(self.results))
        if self.same_library():
            errors = sum(bool(r.get('error')) for r in self.results)
            unsupported = sum(not r.get('error') and not r.get('supported') for r in self.results)
            ready = sum(not r.get('error') and r.get('status') == 'ready' for r in self.results)
            review = sum(not r.get('error') and r.get('supported') and r.get('status') != 'ready' for r in self.results)
            self.progress.setRange(0, len(self.ids))
            self.progress.setValue(min(len(self.ids), len(self.results)))
            summary = _('Processed {processed}/{total}. Results: {ready} ready; {review} to review; {unsupported} insufficient evidence; {errors} errors.').format(
                processed=len(self.results), total=len(self.ids), ready=ready, review=review,
                unsupported=unsupported, errors=errors)
            if global_prefs['developer_mode']:
                summary += ' ' + _('New input tokens: {tokens}.').format(tokens=self.tokens)
            self.status.setText(summary)
        self.update_filters()
        if self.close_requested:
            self.close()

    def apply_row(self, row):
        result = self.results[row]
        if result.get('error') or result.get('applied') or not self.same_library():
            return False
        book_id = result['book_id']
        if not self.db.has_id(book_id):
            self.table.item(row, 6).setText(_('Book removed; skipped'))
            return False
        current_metadata = self.editor.snapshot() if self.editor else book_metadata(self.db, book_id)
        if metadata_state(current_metadata) != metadata_state(result['metadata']):
            self.table.item(row, 6).setText(_('Metadata changed; classify again'))
            return False
        proposed = list(self.table.item(row, 3).data(Qt.ItemDataRole.UserRole) or [])
        allowed = {c['name'] for c in self.values['categories'] if c.get('enabled', True)}
        if any(tag not in allowed for tag in proposed):
            self.table.item(row, 6).setText(_('Use only configured category names'))
            return False
        if self.values['tag_mode'] == 'single' and len(proposed) > 1:
            self.table.item(row, 6).setText(_('Single-tag mode: choose only one proposed tag'))
            return False
        if not proposed:
            return False
        if self.editor:
            self.editor.stage(proposed, self.store, self.batch)
            result['applied'] = True
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
            self.table.item(row, 6).setText(_('Added to editor; confirm with OK'))
            self.update_filters()
            self.update_single_applied(result)
            return True
        field = self.values['destination']
        with self.store.lock:
            before = list(self.db.field_for(field, book_id) or [])
            after = merge_tags(before, proposed)
            if after != before:
                entry = self.store.record(book_id, field, before, after, self.batch)
                self.db.set_field(field, {book_id: after}, allow_case_change=False)
                entry['after'] = list(self.db.field_for(field, book_id) or [])
                entry['state'] = 'applied'
                self.store.save()
        result['applied'] = True
        self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table.item(row, 6).setText(_('Applied'))
        self.gui.library_view.model().refresh_ids([book_id])
        self.gui.tags_view.recount()
        self.update_filters()
        self.update_single_applied(result)
        return True

    def update_single_applied(self, result):
        if self.single_panel and self.single_panel.result is result:
            self.single_panel.confirm_button.setEnabled(False)
            self.single_panel.reason.setText(self.row_status(result))
            self.status.setText(self.row_status(result))

    def apply_checked(self):
        if not self.same_library():
            return self.invalidate()
        try:
            count = sum(self.apply_row(row) for row in range(len(self.results))
                        if self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
            self.status.setText(_('Applied to {count} books.').format(count=count))
        except Exception:
            QMessageBox.warning(self, _('Apply'), _('Could not apply tags. Check the journal before retrying.'))

    def export_results(self):
        path, _filter = QFileDialog.getSaveFileName(self, _('Export results (CSV)'), 'jev-results.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['book_id', 'title', 'mode', 'source', 'model', 'status',
                                 'proposed_tags', 'input_characters', 'new_input_tokens', 'evidence_probability', 'decision_reason', 'verified_by_user', 'machine_suggested_tags']
                                + [c['name'] for c in self.values['categories'] if c.get('enabled', True)])
                def cell(value):
                    # Spreadsheet formulas from book titles must remain plain text.
                    text = str(value)
                    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text
                for row, result in enumerate(self.results):
                    evaluation = result.get('evaluation', {})
                    probabilities = evaluation.get('probabilities', {})
                    values = [result.get('book_id', ''), result['title'], self.values['mode'],
                              result.get('source', ''), evaluation.get('model', ''),
                              self.table.item(row, 6).text(), ', '.join(self.table.item(row, 3).data(Qt.ItemDataRole.UserRole) or []),
                              result.get('input_chars', 0), result.get('tokens_billed', 0),
                              probabilities.get('evidence', ''), result.get('reason', ''), bool(result.get('verified')), ', '.join(result.get('tags', []))]
                    values += [probabilities.get('cat_' + c['id'], '') for c in self.values['categories'] if c.get('enabled', True)]
                    writer.writerow([cell(value) for value in values])
        except OSError:
            QMessageBox.warning(self, _('Export results (CSV)'), _('Could not save file.'))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.close_requested = True
            self.cancel_work()
            event.ignore()
        else:
            for dialog in self.detail_dialogs:
                dialog.reject()
            event.accept()

    def reject(self):
        self.close()
