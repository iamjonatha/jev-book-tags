import json
import threading
import uuid

from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
                     QComboBox, QDoubleSpinBox, QSpinBox, QTableWidget,
                     QTableWidgetItem, QPushButton, QLabel, QMessageBox,
                     QFileDialog, Qt, QThread, pyqtSignal, QCheckBox)
from . import settings as prefs
from .core import validate_settings
from .client import JevClient, JevError, Cancelled
from .branding import DEFAULT_MODEL

try:
    load_translations()
except NameError:
    from calibre.utils.localization import _

_connection_threads = set()


class ConnectionThread(QThread):
    result = pyqtSignal(bool)

    def __init__(self, key):
        super().__init__()
        self.key, self.cancel = key, threading.Event()

    def run(self):
        try:
            JevClient(self.key, self.cancel).models()
            self.result.emit(True)
        except (JevError, Cancelled):
            self.result.emit(False)
        finally:
            self.key = ''


class ConfigWidget(QWidget):
    def __init__(self, db=None, parent=None, gui=None):
        super().__init__(parent)
        self.db = db
        self.gui = gui
        self.values = prefs.load_settings(db)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.key = QLineEdit(prefs.api_key())
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_('API key'), self.key)
        self.advanced_toggle = QCheckBox(_('Advanced options'))
        self.advanced = QWidget(self)
        advanced_form = QFormLayout(self.advanced)
        self.advanced.setVisible(False)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.model = QComboBox()
        self.model.addItems(['jev-latest', 'jev-preview'])
        self.model.setCurrentText(self.values['model'])
        advanced_form.addRow(_('Model'), self.model)
        self.key.setPlaceholderText(_('Enter your TypeSafe AI API key'))
        self.remember = QCheckBox(_('Remember the key in the system keychain'))
        self.remember.setEnabled(prefs.credentials.available)
        self.remember.setChecked(prefs.global_prefs['remember_key'])
        form.addRow('', self.remember)
        self.mode = QComboBox()
        for label, value in ((_('Automatic'), 'auto'), (_('Metadata only'), 'metadata'),
                             (_('Metadata and EPUB excerpts'), 'content')):
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(self.mode.findData(self.values['mode']))
        advanced_form.addRow(_('Input'), self.mode)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.5, 1)
        self.threshold.setSingleStep(0.05)
        self.threshold.setValue(self.values['threshold'])
        self.threshold.setToolTip(_('A tag must exceed 50% and reach its own threshold to be assigned automatically. Below-threshold candidates require your confirmation.'))
        advanced_form.addRow(_('Assignment threshold'), self.threshold)
        self.tag_mode = QComboBox()
        self.tag_mode.addItem(_('Multiple tags above their thresholds'), 'multiple')
        self.tag_mode.addItem(_('One tag only'), 'single')
        self.tag_mode.setCurrentIndex(max(0, self.tag_mode.findData(self.values['tag_mode'])))
        advanced_form.addRow(_('Assign'), self.tag_mode)
        self.tie_margin = QDoubleSpinBox()
        self.tie_margin.setRange(0, 25)
        self.tie_margin.setSuffix(' %')
        self.tie_margin.setValue(self.values['tie_margin'] * 100)
        self.tie_margin.setToolTip(_('Percentage points from the best score. In single-tag mode a close competitor requires review. In multi-tag mode a close candidate below its own threshold remains optional, never automatically assigned.'))
        advanced_form.addRow(_('Close-probability tolerance'), self.tie_margin)
        self.limit = QSpinBox()
        self.limit.setRange(2000, 24000)
        self.limit.setSingleStep(1000)
        self.limit.setValue(self.values['max_chars'])
        advanced_form.addRow(_('Maximum EPUB text characters'), self.limit)
        self.editor_position = QComboBox()
        for label, value in ((_('B — Icon next to Tags'), 'tags'),
                             (_('C — Dedicated row above the bottom buttons'), 'row'),
                             (_('A — Bottom button bar'), 'bottom')):
            self.editor_position.addItem(label, value)
        self.editor_position.setCurrentIndex(max(0, self.editor_position.findData(self.values['editor_position'])))
        form.addRow(_('Metadata editor button'), self.editor_position)
        self.editor_position.setToolTip(_('Applies when the metadata editor is next opened.'))
        layout.addLayout(form)
        layout.addWidget(self.advanced_toggle)
        layout.addWidget(self.advanced)
        self.developer_mode = QCheckBox(_('Enable developer mode'))
        self.developer_mode.setToolTip(_('Show sent input and technical processing statistics.'))
        self.developer_mode.setChecked(prefs.global_prefs['developer_mode'])
        layout.addWidget(self.developer_mode)
        note = QLabel(_('Without Remember, the API key stays in memory for this session.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.test = QPushButton(_('Test connection'))
        self.test.clicked.connect(self.test_connection)
        layout.addWidget(self.test)
        category_note = QLabel(_('Tag labels are saved exactly as entered. Changing the interface language does not rename existing tags.'))
        category_note.setWordWrap(True)
        layout.addWidget(category_note)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([_('Enabled'), _('Tag'), _('Description / inclusion rules'), _('Threshold (optional)')])
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 360)
        self.table.setColumnWidth(3, 150)
        self.table.horizontalHeaderItem(3).setToolTip(_('Optional override of the global threshold: enter 0.95 for 95%, or leave empty to use the global value.'))
        self.table.setColumnHidden(3, not self.advanced_toggle.isChecked())
        self.advanced_toggle.toggled.connect(lambda checked: self.table.setColumnHidden(3, not checked))
        for cat in self.values['categories']:
            self.add_category(cat)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, callback in ((_('Add tag'), lambda: self.add_category()),
                                (_('Remove tag'), self.remove_category),
                                (_('Import tag vocabulary'), self.import_categories),
                                (_('Export tag vocabulary'), self.export_categories)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        for label, callback in ((_('Import profile'), self.import_profile),
                                (_('Export profile'), self.export_profile)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def add_category(self, cat=None):
        if self.table.rowCount() >= 100:
            return
        cat = cat or {'id': uuid.uuid4().hex, 'name': '', 'description': '', 'enabled': True}
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        check.setCheckState(Qt.CheckState.Checked if cat.get('enabled', True) else Qt.CheckState.Unchecked)
        check.setData(Qt.ItemDataRole.UserRole, cat['id'])
        self.table.setItem(row, 0, check)
        for col, text in ((1, cat['name']), (2, cat['description']), (3, str(cat.get('threshold') or ''))):
            self.table.setItem(row, col, QTableWidgetItem(text))

    def remove_category(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def categories(self):
        result = []
        for row in range(self.table.rowCount()):
            threshold = self.table.item(row, 3).text().strip().replace(',', '.')
            result.append({'id': self.table.item(row, 0).data(Qt.ItemDataRole.UserRole),
                           'enabled': self.table.item(row, 0).checkState() == Qt.CheckState.Checked,
                           'name': self.table.item(row, 1).text().strip(),
                           'description': self.table.item(row, 2).text().strip(),
                           'threshold': float(threshold) if threshold else None})
        return result

    def get_settings(self):
        return {'model': self.model.currentText(), 'mode': self.mode.currentData(),
                'threshold': self.threshold.value(), 'max_chars': self.limit.value(),
                'tag_mode': self.tag_mode.currentData(), 'tie_margin': self.tie_margin.value() / 100,
                'editor_position': self.editor_position.currentData(),
                'destination': 'tags', 'categories': self.categories()}

    def apply_settings(self, values):
        self.model.setCurrentText(values['model'])
        self.mode.setCurrentIndex(self.mode.findData(values['mode']))
        self.threshold.setValue(values['threshold'])
        self.limit.setValue(values['max_chars'])
        self.tag_mode.setCurrentIndex(self.tag_mode.findData(values['tag_mode']))
        self.tie_margin.setValue(values['tie_margin'] * 100)
        self.editor_position.setCurrentIndex(self.editor_position.findData(values['editor_position']))
        self.table.setRowCount(0)
        for cat in values['categories']:
            self.add_category(cat)

    def import_profile(self):
        path, _filter = QFileDialog.getOpenFileName(self, _('Import profile'), '', 'JSON (*.json)')
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as stream:
                profile = json.load(stream)
            if (not isinstance(profile, dict) or profile.get('format') != 'jev-book-tags-profile'
                    or profile.get('version') != 1 or not isinstance(profile.get('settings'), dict)):
                raise ValueError('Unsupported profile')
            values = profile['settings']
            expected = {'model', 'mode', 'threshold', 'max_chars', 'tag_mode', 'tie_margin',
                        'editor_position', 'destination', 'categories'}
            if (set(values) != expected or values['model'] not in ('jev-latest', 'jev-preview')
                    or values['destination'] != 'tags'):
                raise ValueError('Invalid profile fields')
            validate_settings(values)
        except (OSError, ValueError, KeyError, TypeError):
            QMessageBox.warning(self, _('Configuration'), _('Invalid profile file.'))
            return
        self.apply_settings(values)

    def export_profile(self):
        if not self.validate():
            return
        path, _filter = QFileDialog.getSaveFileName(self, _('Export profile'), 'jev-profile.json', 'JSON (*.json)')
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as stream:
                json.dump({'format': 'jev-book-tags-profile', 'version': 1,
                           'settings': self.get_settings()}, stream, ensure_ascii=False, indent=2)
        except OSError:
            QMessageBox.warning(self, _('Export profile'), _('Could not save file.'))

    def validate(self):
        try:
            validate_settings(self.get_settings())
            return True
        except (ValueError, KeyError, TypeError):
            QMessageBox.warning(self, _('Configuration'), _('Check category names, unique IDs and thresholds between 0.5 and 1.'))
            return False

    def save_settings(self):
        prefs.save_key(self.key.text(), self.remember.isChecked())
        prefs.save_settings(self.get_settings(), self.db)
        prefs.global_prefs['developer_mode'] = self.developer_mode.isChecked()

    def import_categories(self):
        path, _filter = QFileDialog.getOpenFileName(self, _('Import tag vocabulary'), '', 'JSON (*.json)')
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as stream:
                cats = json.load(stream)['categories']
            values = self.get_settings()
            values['categories'] = cats
            validate_settings(values)
        except (OSError, ValueError, KeyError, TypeError):
            QMessageBox.warning(self, _('Configuration'), _('Invalid category file.'))
            return
        self.table.setRowCount(0)
        for cat in cats:
            self.add_category(cat)

    def export_categories(self):
        if not self.validate():
            return
        path, _filter = QFileDialog.getSaveFileName(self, _('Export tag vocabulary'), 'jev-tags.json', 'JSON (*.json)')
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as stream:
                    json.dump({'version': 1, 'categories': self.categories()}, stream, ensure_ascii=False, indent=2)
            except OSError:
                QMessageBox.warning(self, _('Configuration'), _('Could not save file.'))

    def test_connection(self):
        if not self.key.text().strip():
            QMessageBox.warning(self, _('Connection'), _('Enter an API key first.'))
            return
        worker = ConnectionThread(self.key.text())
        _connection_threads.add(worker)
        self.test.setEnabled(False)
        worker.result.connect(self.connection_result)
        worker.finished.connect(lambda: _connection_threads.discard(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def connection_result(self, success):
        self.test.setEnabled(True)
        QMessageBox.information(self, _('Connection'), _('Connection successful.') if success else _('Connection failed. Check the key and network.'))
