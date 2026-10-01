"""Scoped Qt integration: stage tags in calibre's metadata form, never save it implicitly."""
from qt.core import QObject, QEvent, QDialog, QDialogButtonBox, QPushButton, QGridLayout, QHBoxLayout, QSize, QWidget
from calibre.gui2.metadata.single import MetadataSingleDialogBase

from .branding import NAME, icon
from .core import merge_tags
from .settings import load_settings

try:
    load_translations()
except NameError:
    from calibre.utils.localization import _


def metadata_values(mi):
    return {'title': mi.title, 'authors': mi.authors or [], 'comments': mi.comments or '',
            'languages': mi.languages or [], 'series': mi.series}


class EditorContext:
    def __init__(self, editor, legacy):
        self.editor, self.legacy, self.pending = editor, legacy, []
        editor.accepted.connect(lambda: self.reconcile(final=True))
        editor.finished.connect(lambda _: self.reconcile(final=True))
        editor.next_button.clicked.connect(self.reconcile)
        editor.prev_button.clicked.connect(self.reconcile)

    def snapshot(self):
        return metadata_values(self.editor.to_book_metadata())

    def valid(self, book_id):
        return self.editor.db is self.legacy and self.editor.book_id == book_id

    def tags(self):
        return list(self.editor.tags.current_val or [])

    def stage(self, proposed, store, batch):
        before = self.tags()
        after = merge_tags(before, proposed)
        if after != before:
            entry = store.record(self.editor.book_id, 'tags', before, after, batch)
            entry['state'] = 'editor_pending'
            store.save()
            self.pending.append((store, entry))
            self.editor.tags.set_value(after)
            self.editor.was_data_edited = True

    def reconcile(self, _checked=False, final=False):
        remaining, groups = [], {}
        for store, entry in self.pending:
            if not final and self.editor.book_id == entry['book_id']:
                remaining.append((store, entry))
                continue
            groups.setdefault((str(store.path), entry['book_id']), []).append((store, entry))
        for items in groups.values():
            store, tail = items[-1]
            with store.lock:
                db = self.legacy.new_api
                current = list(db.field_for('tags', tail['book_id']) or []) if db.has_id(tail['book_id']) else []
                canonical = lambda values: sorted(v.casefold() for v in values)
                committed = canonical(current) == canonical(tail['after'])
                for _store, entry in items:
                    entry['state'] = 'applied' if committed else 'discarded'
                store.save()
        self.pending = remaining


class MetadataEditorHook(QObject):
    def __init__(self, action):
        super().__init__(action)
        self.action = action

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, MetadataSingleDialogBase):
            self.attach(watched)
        return False

    def attach(self, editor):
        if getattr(editor, '_jev_tags_button', None) is not None:
            return
        if (editor.db is not self.action.gui.current_db or editor.parent() is not self.action.gui
                or not hasattr(editor, 'book_id')):
            return
        label = _('Classify with {name}').format(name=NAME)
        button = QPushButton(icon(), label, editor)
        button.setAccessibleName(label)
        button.setAutoDefault(False)
        button.setToolTip(_('Use the current form values and add suggested tags here. OK saves them; Cancel discards them.'))
        context = EditorContext(editor, self.action.gui.current_db)
        button.clicked.connect(lambda: self.action.run_editor(context))
        position = load_settings(self.action.gui.current_db.new_api)['editor_position']
        if position == 'tags' and self.place_by_tags(editor, button):
            button.setText('')
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(32, max(28, editor.tags.sizeHint().height()))
        elif position == 'bottom':
            editor.button_box.addButton(button, QDialogButtonBox.ButtonRole.ActionRole)
        else:
            # Also a safe fallback if a future calibre layout moves the tags.
            editor.l.insertWidget(editor.l.count() - 1, button)
            position = 'row'
        editor._jev_tags_position = position
        editor._jev_tags_button = button
        editor._jev_tags_context = context

    @staticmethod
    def place_by_tags(editor, button):
        for grid in editor.findChildren(QGridLayout):
            index = grid.indexOf(editor.tags)
            if index < 0:
                continue
            row, column, row_span, column_span = grid.getItemPosition(index)
            alignment = grid.itemAt(index).alignment()
            grid.removeWidget(editor.tags)
            line = QHBoxLayout()
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(4)
            line.addWidget(editor.tags, 1)
            line.addWidget(button)
            grid.addLayout(line, row, column, row_span, column_span, alignment)
            QWidget.setTabOrder(editor.tags, button)
            QWidget.setTabOrder(button, editor.clear_tags_button)
            editor._jev_tags_layout = line
            return True
        return False
