import copy
import os

from calibre.utils.config import JSONConfig
from calibre.constants import config_dir
from .core import DEFAULTS, validate_settings
from .branding import DEFAULT_MODEL
from .credentials import CredentialStore, CredentialError

SESSION_KEY = ''
_stored_key = None
credentials = CredentialStore(config_dir)
global_prefs = JSONConfig('plugins/jev_catalog')
global_prefs.defaults['settings'] = DEFAULTS
global_prefs.defaults['remember_key'] = False
PREF_NAME = 'jev_catalog_settings'


def api_key():
    global _stored_key
    if SESSION_KEY:
        return SESSION_KEY
    environment = os.environ.get('TYPESAFE_API_KEY', '').strip()
    if environment:
        return environment
    if _stored_key is None:
        try:
            _stored_key = credentials.read() if global_prefs['remember_key'] else ''
        except CredentialError:
            _stored_key = ''
    return _stored_key


def save_key(key, remember):
    global SESSION_KEY, _stored_key
    key = key.strip()
    if key and (not key.isascii() or not key.isprintable() or any(c.isspace() for c in key)):
        raise ValueError('Invalid API key')
    if remember and key:
        credentials.write(key)
    elif global_prefs['remember_key']:
        credentials.delete()
    global_prefs['remember_key'] = bool(remember and key)
    SESSION_KEY, _stored_key = key, key if remember else ''


def load_settings(db=None):
    stored = db.pref(PREF_NAME, default=None) if db else None
    result = copy.deepcopy(DEFAULTS)
    result.update(copy.deepcopy(stored or global_prefs['settings']))
    if result.get('model') not in ('jev-latest', 'jev-preview'):
        result['model'] = DEFAULT_MODEL
    result['destination'] = 'tags'
    return result


def save_settings(settings, db=None):
    validate_settings(settings)
    settings = copy.deepcopy(settings)
    if db:
        db.set_pref(PREF_NAME, copy.deepcopy(settings))
    else:
        global_prefs['settings'] = copy.deepcopy(settings)


def library_identity(legacy_db):
    return str(legacy_db.new_api.library_id) + ':' + os.path.realpath(legacy_db.library_path)
