"""Read-only pipeline; caller controls all database writes."""
import zipfile
import xml.etree.ElementTree as ET

from .client import Cancelled
from .core import (metadata_state, questions, validate_response, decide,
                   should_enrich, fingerprint)
from .extract import extract_epub


def classify(metadata, settings, client, store, content_loader=None):
    state = metadata_state(metadata)
    used, warning, tokens = 'metadata', '', 0
    enriched = False

    def enrich():
        nonlocal enriched, used, warning
        enriched = True
        if content_loader is None:
            warning = 'no_epub'
            return
        try:
            with content_loader() as source:
                material = extract_epub(source, settings['max_chars'])
            state['book'].update(material)
            used = 'content'
            if not material['excerpts']:
                warning = 'no_text'
        except Cancelled:
            raise
        except (OSError, ValueError, KeyError, StopIteration, zipfile.BadZipFile, ET.ParseError):
            warning = 'extract_failed'

    def evaluate():
        nonlocal tokens, last_fingerprint
        if client.cancel.is_set():
            raise Cancelled()
        cache_key = fingerprint(state, settings)
        last_fingerprint = cache_key
        cached = store.data['cache'].get(cache_key)
        if cached is None:
            value = validate_response(client.evaluate(state, questions(settings), settings['model']), questions(settings))
            tokens += value['input_tokens']
            store.cache(cache_key, value)
        else:
            value = cached
        has_material = len(state['book']['description']) >= 200 or bool(state['book'].get('excerpts'))
        return value, decide(value, settings, has_material)

    if settings['mode'] == 'content' or (settings['mode'] == 'auto' and should_enrich(state)):
        enrich()
    last_fingerprint = ''
    evaluation, decision = evaluate()
    if settings['mode'] == 'auto' and not enriched and should_enrich(state, decision):
        enrich()
        if used == 'content':
            evaluation, decision = evaluate()
    if settings['mode'] == 'content' and (warning or used != 'content'):
        decision['status'] = 'review'
        decision['reason'] = 'content_unavailable'
    return {**decision, 'evaluation': evaluation, 'source': used,
            'warning': warning, 'tokens_billed': tokens, 'input_chars': len(str(state)),
            'input_fingerprint': last_fingerprint}
