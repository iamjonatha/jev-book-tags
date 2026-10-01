"""Atomic local cache and write-ahead audit trail, with no credentials."""
import hashlib
import json
import os
import threading
from pathlib import Path
from datetime import datetime, timezone


class Store:
    def __init__(self, root, library_id):
        self.lock = threading.RLock()
        self.path = Path(root) / (hashlib.sha256(library_id.encode()).hexdigest() + '.json')
        self.data = {'version': 1, 'cache': {}, 'journal': []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding='utf-8'))
                if self.data.get('version') != 1 or not isinstance(self.data['cache'], dict) or not isinstance(self.data['journal'], list):
                    raise ValueError('Invalid store')
            except (ValueError, KeyError, TypeError):
                raise ValueError('Local journal is unreadable; preserve it before resetting') from None

    def save(self):
        with self.lock:
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf-8') as stream:
            json.dump(self.data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)

    def cache(self, key, evaluation):
        with self.lock:
            self.data['cache'][key] = evaluation
            self.save()

    def record(self, book_id, field, before, after, batch):
        entry = {'book_id': book_id, 'field': field, 'before': list(before), 'after': list(after),
                 'time': datetime.now(timezone.utc).isoformat(), 'state': 'pending', 'batch': batch}
        with self.lock:
            self.data['journal'].append(entry)
            self.save()
            return entry
