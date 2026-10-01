import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('jev_test_plugin')
package.__path__ = [str(ROOT / 'plugin')]
sys.modules['jev_test_plugin'] = package
from jev_test_plugin.core import (DEFAULTS, questions, validate_response, decide,
                                  validate_settings, merge_tags, fingerprint)
from jev_test_plugin.engine import classify
from jev_test_plugin.extract import extract_epub
from jev_test_plugin.storage import Store
from jev_test_plugin.client import JevClient, JevError, Cancelled


def epub_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles></container>')
        manifest = '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
        manifest += ''.join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(10))
        spine = ''.join(f'<itemref idref="c{i}"/>' for i in range(10))
        z.writestr('OPS/package.opf', f'<package xmlns="http://www.idpf.org/2007/opf"><manifest>{manifest}</manifest><spine>{spine}</spine></package>')
        z.writestr('OPS/nav.xhtml', '<nav>Science and history chapters</nav>')
        for i in range(10):
            z.writestr(f'OPS/c{i}.xhtml', f'<html><script>HIDDEN</script><p>Chapter {i}: ' + ('scientific historical discussion ' * 100) + '</p></html>')
    return stream.getvalue()


def response(qs, evidence=0.99, category=0.99):
    return {'model': 'jev-test', 'usage': {'input_tokens': 100},
            'answers': {k: {'type': 'noul', 'noul': evidence if k == 'evidence' else category} for k in qs}}


class FakeClient:
    def __init__(self, responses=None):
        self.cancel, self.calls, self.responses = threading.Event(), [], list(responses or [])

    def evaluate(self, state, qs, model):
        self.calls.append(copy.deepcopy(state))
        return self.responses.pop(0) if self.responses else response(qs)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.values = copy.deepcopy(DEFAULTS)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name, 'library-one')

    def test_reject_invalid_taxonomy(self):
        self.values['categories'][1]['name'] = self.values['categories'][0]['name'].upper()
        with self.assertRaises(ValueError):
            validate_settings(self.values)

    def test_response_rejects_missing_wrong_type_and_nonfinite(self):
        qs = questions(self.values)
        for bad in (None, True, -0.1, 1.1, float('nan'), '0.9'):
            value = response(qs)
            value['answers']['evidence']['noul'] = bad
            with self.assertRaises(ValueError):
                validate_response(value, qs)
        value = response(qs)
        value['answers'].pop('evidence')
        with self.assertRaises(ValueError):
            validate_response(value, qs)

    def test_title_only_cannot_be_autoassigned_even_with_high_probability(self):
        value = validate_response(response(questions(self.values)), questions(self.values))
        result = decide(value, self.values, False)
        self.assertEqual(result['tags'], [])
        self.assertEqual(result['status'], 'review')

    def test_excluded_uncertain_category_does_not_block_confident_tags(self):
        qs = questions(self.values)
        value = response(qs)
        value['answers']['cat_history']['noul'] = 0.6
        result = decide(validate_response(value, qs), self.values, True)
        self.assertEqual(result['status'], 'ready')
        self.assertIn('Biography', result['tags'])
        self.assertNotIn('History', result['tags'])

    def test_cache_reused_and_threshold_changes_redecide_without_billing(self):
        self.values['mode'] = 'metadata'
        metadata = {'title': 'History', 'comments': 'Historical facts and biography. ' * 20}
        client = FakeClient()
        first = classify(metadata, self.values, client, self.store)
        self.values['threshold'] = 1
        second = classify(metadata, self.values, client, self.store)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(first['tokens_billed'], 100)
        self.assertEqual(second['tokens_billed'], 0)
        self.assertEqual(second['status'], 'review')

    def test_close_probabilities_multiple_mode_keeps_both(self):
        qs = questions(self.values)
        result = response(qs, category=0.05)
        result['answers']['cat_history']['noul'] = 0.9
        result['answers']['cat_biography']['noul'] = 0.84
        decision = decide(validate_response(result, qs), self.values, True)
        self.assertEqual(decision['tags'], ['History'])
        self.assertEqual(decision['status'], 'ready')

    def test_close_probabilities_single_mode_requires_review(self):
        self.values['tag_mode'] = 'single'
        qs = questions(self.values)
        result = response(qs, category=0.05)
        result['answers']['cat_history']['noul'] = 0.9
        result['answers']['cat_biography']['noul'] = 0.89
        decision = decide(validate_response(result, qs), self.values, True)
        self.assertEqual(decision['tags'], ['History'])
        self.assertEqual(decision['status'], 'review')

    def test_low_close_probabilities_never_assign_tags(self):
        qs = questions(self.values)
        decision = decide(validate_response(response(qs, category=0.2), qs), self.values, True)
        self.assertEqual(decision['tags'], [])
        self.assertEqual(decision['status'], 'review')

    def test_close_but_below_threshold_are_suggestions_only(self):
        qs = questions(self.values)
        result = response(qs, category=0.05)
        result['answers']['cat_history']['noul'] = 0.8
        result['answers']['cat_biography']['noul'] = 0.79
        decision = decide(validate_response(result, qs), self.values, True)
        self.assertEqual(decision['tags'], ['History', 'Biography'])
        self.assertEqual(decision['status'], 'review')

    def test_threshold_and_tie_matrix(self):
        qs = questions(self.values)
        for first, second, mode, expected, status in (
                (.90, .88, 'multiple', ['History', 'Biography'], 'ready'),
                (.90, .84, 'multiple', ['History'], 'ready'),
                (.80, .79, 'multiple', ['History', 'Biography'], 'review'),
                (.90, .88, 'single', ['History'], 'review'),
                (.90, .82, 'single', ['History'], 'review'),
                (.90, .81, 'single', ['History'], 'ready'),
                (.85, .05, 'multiple', ['History'], 'ready'),
                (.849, .05, 'multiple', ['History'], 'review'),
                (.50, .49, 'multiple', [], 'review')):
            with self.subTest(first=first, second=second, mode=mode):
                self.values['tag_mode'] = mode
                value = response(qs, category=.01)
                value['answers']['cat_history']['noul'] = first
                value['answers']['cat_biography']['noul'] = second
                decision = decide(validate_response(value, qs), self.values, True)
                self.assertEqual(decision['tags'], expected)
                self.assertEqual(decision['status'], status)

    def test_category_threshold_is_not_bypassed_by_close_probability(self):
        self.values['categories'][1]['threshold'] = .95
        qs = questions(self.values)
        value = response(qs, category=.01)
        value['answers']['cat_history']['noul'] = .90
        value['answers']['cat_biography']['noul'] = .89
        decision = decide(validate_response(value, qs), self.values, True)
        self.assertEqual(decision['tags'], ['History'])
        self.assertEqual(decision['status'], 'ready')

    def test_explicit_review_reasons_and_evidence_boundary(self):
        qs = questions(self.values)
        value = response(qs, category=.9)
        for evidence, material, reason in ((.80, True, 'ready'), (.799, True, 'low_evidence'), (.99, False, 'missing_material')):
            value['answers']['evidence']['noul'] = evidence
            self.assertEqual(decide(validate_response(value, qs), self.values, material)['reason'], reason)

    def test_auto_enriches_short_metadata_before_call(self):
        client = FakeClient()
        result = classify({'title': 'Unknown'}, self.values, client, self.store,
                          lambda: io.BytesIO(epub_bytes()))
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result['source'], 'content')
        self.assertEqual(result['status'], 'ready')

    def test_auto_retries_with_content_for_uncertain_metadata(self):
        qs = questions(self.values)
        client = FakeClient([response(qs, category=0.6), response(qs)])
        metadata = {'title': 'History', 'comments': 'Historical facts and biography. ' * 20}
        result = classify(metadata, self.values, client, self.store, lambda: io.BytesIO(epub_bytes()))
        self.assertEqual(len(client.calls), 2)
        self.assertNotIn('excerpts', client.calls[0]['book'])
        self.assertIn('excerpts', client.calls[1]['book'])
        self.assertEqual(result['tokens_billed'], 200)

    def test_content_mode_missing_epub_requires_review(self):
        self.values['mode'] = 'content'
        result = classify({'comments': 'Meaningful history description. ' * 20}, self.values, FakeClient(), self.store)
        self.assertEqual(result['status'], 'review')
        self.assertEqual(result['warning'], 'no_epub')

    def test_corrupt_epub_falls_back(self):
        result = classify({'title': 'Unknown'}, self.values, FakeClient(), self.store, lambda: io.BytesIO(b'broken'))
        self.assertEqual(result['warning'], 'extract_failed')
        self.assertEqual(result['tags'], [])

    def test_epub_reading_order_distributed_samples_and_budget(self):
        result = extract_epub(io.BytesIO(epub_bytes()), 4000)
        self.assertTrue(result['excerpts'])
        self.assertEqual(result['excerpts'][0]['spine_position'], 1)
        self.assertEqual(result['excerpts'][-1]['spine_position'], 10)
        text = ''.join(e['text'] for e in result['excerpts'])
        self.assertNotIn('HIDDEN', text)
        self.assertLessEqual(len(text) + len(result['table_of_contents']), 4000)

    def test_merge_preserves_manual_tags_and_case(self):
        self.assertEqual(merge_tags(['Manual', 'history'], ['History', 'Biography']), ['Manual', 'history', 'Biography'])

    def test_store_is_library_specific_and_journal_survives_restart(self):
        entry = self.store.record(1, 'tags', ['manual'], ['manual', 'History'], 'batch1')
        self.assertEqual(entry['state'], 'pending')
        self.assertEqual(Store(self.temp.name, 'library-one').data['journal'][0], entry)
        self.assertEqual(Store(self.temp.name, 'library-two').data['journal'], [])

    def test_taxonomy_changes_invalidate_cache(self):
        key = fingerprint({}, self.values)
        self.values['categories'][0]['description'] += ' New boundaries.'
        self.assertNotEqual(key, fingerprint({}, self.values))


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Opener:
    def __init__(self, results):
        self.results, self.calls = list(results), []

    def open(self, request, timeout):
        self.calls.append(request)
        value = self.results.pop(0)
        if isinstance(value, Exception):
            raise value
        return Reply(json.dumps(value).encode())


class ClientTests(unittest.TestCase):
    def test_request_uses_official_endpoint_auth_and_json(self):
        opener = Opener([{'answers': {}}])
        JevClient('test-key', opener=opener).evaluate({'book': {}}, {}, 'jev-test')
        req = opener.calls[0]
        self.assertEqual(req.full_url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(req.get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(json.loads(req.data)['model'], 'jev-test')

    def test_auth_failure_redacts_service_body(self):
        error = urllib.error.HTTPError('url', 401, 'SECRET test-key', {}, io.BytesIO(b'test-key'))
        with self.assertRaises(JevError) as caught:
            JevClient('test-key', opener=Opener([error])).models()
        self.assertEqual(str(caught.exception), 'Invalid API key')
        self.assertNotIn('test-key', str(caught.exception))

    def test_rate_limit_retry_and_cancel(self):
        class NoWait:
            def is_set(self): return False
            def wait(self, delay): return False
        error = urllib.error.HTTPError('url', 429, '', {'Retry-After': '1'}, io.BytesIO())
        opener = Opener([error, {'models': []}])
        self.assertEqual(JevClient('key', cancel=NoWait(), opener=opener).models(), {'models': []})
        self.assertEqual(len(opener.calls), 2)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            JevClient('key', cancel=cancel, opener=Opener([])).models()

    def test_network_timeout_is_not_automatically_rebilled(self):
        opener = Opener([TimeoutError()])
        with self.assertRaises(JevError):
            JevClient('key', opener=opener).evaluate({}, {}, 'jev-test')
        self.assertEqual(len(opener.calls), 1)


if __name__ == '__main__':
    unittest.main()
