"""Minimal official TypeSafe HTTP client. No third-party dependencies."""
import json
import threading
import urllib.error
import urllib.request

BASE_URL = 'https://api.typesafe.ai/v1'


class JevError(Exception):
    pass


class Cancelled(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class JevClient:
    def __init__(self, key, cancel=None, opener=None, timeout=15):
        self.key = key.strip()
        if not self.key or not self.key.isascii() or not self.key.isprintable() or any(c.isspace() for c in self.key):
            raise JevError('A valid API key is required')
        self.cancel = cancel or threading.Event()
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.timeout = timeout

    def request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(BASE_URL + path, data=body, headers={
            'Authorization': 'Bearer ' + self.key,
            'Content-Type': 'application/json', 'User-Agent': 'CalibreJevCatalog/0.1',
        })
        for attempt in range(3):
            if self.cancel.is_set():
                raise Cancelled()
            try:
                with self.opener.open(req, timeout=self.timeout) as reply:
                    raw = reply.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise JevError('Response exceeds size limit')
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise JevError('Invalid JSON response') from None
                if self.cancel.is_set():
                    raise Cancelled()
                return result
            except urllib.error.HTTPError as exc:
                code = exc.code
                retry_after = exc.headers.get('Retry-After', '') if exc.headers else ''
                exc.close()
                if code not in (429, 529, 502, 503, 504) or attempt == 2:
                    messages = {401: 'Invalid API key', 403: 'Access denied',
                                422: 'Invalid API request', 429: 'Rate limit exceeded',
                                529: 'Service overloaded'}
                    raise JevError(messages.get(code, 'HTTP error ' + str(code))) from None
                try:
                    delay = min(30, max(1, float(retry_after)))
                except ValueError:
                    delay = 2 ** (attempt + 1)
                if self.cancel.wait(delay):
                    raise Cancelled()
            except (urllib.error.URLError, TimeoutError, OSError):
                # A timed-out POST might have been billed. Do not blindly retry it.
                raise JevError('Connection failed or timed out') from None

    def models(self):
        result = self.request('/models')
        if not isinstance(result, dict) or not isinstance(result.get('models'), list):
            raise JevError('Invalid models response')
        return result

    def evaluate(self, state, questions, model):
        return self.request('/systemone', {'state': state, 'questions': questions, 'model': model})
