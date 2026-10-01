"""Shared single-book view: selections stay local until explicitly confirmed."""
from qt.core import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                     QToolButton, QGridLayout, QCheckBox, QScrollArea, QSizePolicy, QEvent, QTimer, Qt, pyqtSignal)
from .core import ranked_candidates
from .settings import global_prefs

try:
    load_translations()
except NameError:
    from calibre.utils.localization import _


def reason_text(result):
    if result.get('error'):
        return _('Connection error; processing stopped') if result['error'] == 'connection' else _('Book could not be read')
    return {
        'ready': _('Selected tags reach their thresholds and the evidence is sufficient.'),
        'missing_material': _('A title and author alone are not enough. Add a meaningful description or readable EPUB excerpts.'),
        'low_evidence': _('JEV evidence confidence is below 80%. The available material may not represent the book.'),
        'no_likely_tag': _('No configured category exceeds 50%. Choose manually or improve the category definitions.'),
        'below_threshold': _('No tag reaches its assignment threshold. These are suggestions to confirm manually.'),
        'near_tie': _('Single-tag mode: two or more likely candidates are within the closeness margin. Choose one.'),
        'content_unavailable': _('EPUB excerpts were requested but are unavailable. Confirm a metadata-based choice manually.'),
    }.get(result.get('reason'), _('Review required'))


class TagChoicePanel(QWidget):
    confirmed = pyqtSignal(object)
    inspect_input = pyqtSignal()

    def __init__(self, result, values, label, parent=None):
        super().__init__(parent)
        self.result, self.values = result, values
        self.buttons = {}
        self._changing = False
        layout = QVBoxLayout(self)
        title = QLabel(result['title'])
        title.setWordWrap(True)
        font = title.font(); font.setBold(True); title.setFont(font)
        layout.addWidget(title)
        authors = result.get('metadata', {}).get('authors', [])
        author_label = QLabel(' & '.join(authors)); author_label.setWordWrap(True)
        layout.addWidget(author_label)
        self.reason = QLabel(reason_text(result)); self.reason.setWordWrap(True)
        layout.addWidget(self.reason)
        source = _('Metadata + excerpts') if result.get('source') == 'content' else _('Metadata')
        evidence = result.get('evaluation', {}).get('probabilities', {}).get('evidence', 0)
        summary = QLabel(_('Input: {source}. Evidence confidence: {evidence:.0%}.').format(source=source, evidence=evidence) if result.get('evaluation') else _('No evaluation is available for this book.'))
        summary.setWordWrap(True); layout.addWidget(summary)
        warning = {'no_epub': _('No EPUB available'), 'no_text': _('No readable excerpts'),
                   'extract_failed': _('EPUB extraction failed')}.get(result.get('warning'), '')
        if warning:
            layout.addWidget(QLabel(warning))
        existing = QLabel(_('Existing tags (preserved): {tags}').format(tags=', '.join(result.get('previous_tags', [])) or _('None')))
        existing.setWordWrap(True); layout.addWidget(existing)
        note = QLabel(_('Click a tag to include or exclude it. Percentages are JEV confidence, not measured accuracy. Below-threshold tags require your explicit confirmation.'))
        note.setWordWrap(True); layout.addWidget(note)
        self.selected = set(result.get('chosen_tags', result.get('tags', [])))
        candidates = ranked_candidates(result['evaluation'], values) if result.get('evaluation') else []
        self.candidates = candidates
        self.area = QScrollArea(self); self.area.setWidgetResizable(True)
        self.area.setMinimumHeight(180)
        self.content = QWidget(); self.grid = QGridLayout(self.content)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.area.setWidget(self.content); layout.addWidget(self.area, 1)
        self.area.viewport().installEventFilter(self)
        for cat in candidates:
            name, probability = cat['name'], cat['probability']
            badge = _('Above threshold') if cat['qualified'] else _('Below threshold')
            if cat['close'] and not cat['qualified']:
                badge = _('Close candidate, below threshold')
            button = QToolButton(self.content); button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            button.setChecked(name in self.selected)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setText(self.chip_text(cat, button.isChecked()))
            button.setAccessibleName(_('{tag}, confidence {probability:.0%}, {state}').format(tag=name, probability=probability, state=badge))
            button.setToolTip(_('{tag}: {state}. Required threshold: {threshold:.0%}.\n{definition}').format(tag=name, state=badge, threshold=cat['effective_threshold'], definition=cat['description']))
            button.toggled.connect(lambda checked, cat=cat: self.toggle(cat, checked))
            self.buttons[name] = button
        self.show_all = QCheckBox(_('Show all categories, including low probabilities'))
        self.show_all.toggled.connect(self.reflow)
        layout.addWidget(self.show_all)
        self.selection_label = QLabel(); self.selection_label.setWordWrap(True)
        layout.addWidget(self.selection_label)
        controls = QHBoxLayout()
        self.inspect = QPushButton(_('View sent input'))
        self.inspect.setEnabled(bool(result.get('input_fingerprint')))
        self.inspect.clicked.connect(lambda: self.inspect_input.emit()); controls.addWidget(self.inspect)
        self.inspect.setVisible(bool(global_prefs['developer_mode']))
        self.confirm_button = QPushButton(label)
        self.confirm_button.clicked.connect(lambda: self.confirmed.emit(self.chosen_tags()))
        self.confirm_button.setEnabled(not result.get('error') and not result.get('applied'))
        controls.addWidget(self.confirm_button); layout.addLayout(controls)
        self.reflow(); self.update_selection()

    def chip_text(self, cat, checked):
        marker = '✓ ' if checked else '+ '
        state = _('Above threshold') if cat['qualified'] else _('Below threshold')
        suffix = ' · ' + format(cat['probability'], '.0%')
        width = getattr(self, '_chip_width', 240) - 20 - self.fontMetrics().horizontalAdvance(marker + suffix)
        name = self.fontMetrics().elidedText(cat['name'], Qt.TextElideMode.ElideRight, max(20, width))
        label = marker + name + suffix
        return label + '\n' + state

    def toggle(self, cat, checked):
        if self._changing:
            return
        self._changing = True
        if checked:
            if self.values['tag_mode'] == 'single':
                self.selected.clear()
                for name, button in self.buttons.items():
                    if name != cat['name']:
                        button.setChecked(False)
            self.selected.add(cat['name'])
        else:
            self.selected.discard(cat['name'])
        for candidate in self.candidates:
            button = self.buttons[candidate['name']]
            button.setText(self.chip_text(candidate, button.isChecked()))
        self._changing = False
        self.update_selection()

    def chosen_tags(self):
        return [c['name'] for c in self.candidates if c['name'] in self.selected]

    def update_selection(self):
        chosen = self.chosen_tags()
        self.selection_label.setText(_('Selected tags: {tags}').format(tags=', '.join(chosen) or _('None')))
        self.confirm_button.setEnabled(bool(chosen) and not self.result.get('error') and not self.result.get('applied'))

    def reflow(self, *_):
        while self.grid.count():
            self.grid.takeAt(0)
        columns = max(1, min(3, self.area.viewport().width() // 230))
        self._chip_width = max(150, (self.area.viewport().width() - 30) // columns)
        visible = 0
        for cat in self.candidates:
            button = self.buttons[cat['name']]
            button.setMaximumWidth(self._chip_width)
            button.setText(self.chip_text(cat, button.isChecked()))
            show = self.show_all.isChecked() or cat['probability'] > 0.5 or cat['name'] in self.selected
            button.setVisible(show)
            if show:
                self.grid.addWidget(button, visible // columns, visible % columns)
                visible += 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'area') and hasattr(self, 'show_all'):
            self.reflow()

    def eventFilter(self, watched, event):
        if watched is self.area.viewport() and event.type() == QEvent.Type.Resize and hasattr(self, 'show_all'):
            QTimer.singleShot(0, self.reflow)
        return super().eventFilter(watched, event)
