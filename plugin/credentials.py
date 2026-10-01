"""Optional OS credential storage. Never use preference JSON for secrets."""
import hashlib
import os
import shlex
import shutil
import subprocess
import sys


class CredentialError(Exception):
    pass


class CredentialStore:
    def __init__(self, profile):
        suffix = hashlib.sha256(os.path.realpath(profile).encode()).hexdigest()[:16]
        self.service = 'org.calibre.jev-catalog.' + suffix

    @property
    def available(self):
        return sys.platform == 'darwin' or (sys.platform.startswith('linux') and bool(shutil.which('secret-tool')))

    def _run(self, arguments, input_text=None):
        try:
            return subprocess.run(arguments, input=input_text, encoding='utf-8',
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise CredentialError('Credential service unavailable') from None

    def read(self):
        if not self.available:
            return ''
        if sys.platform == 'darwin':
            result = self._run(['/usr/bin/security', 'find-generic-password', '-s', self.service, '-a', 'api-key', '-w'])
        else:
            result = self._run(['secret-tool', 'lookup', 'service', self.service, 'account', 'api-key'])
        return result.stdout.strip() if result.returncode == 0 else ''

    def write(self, key):
        if not self.available:
            raise CredentialError('Credential service unavailable')
        if sys.platform == 'darwin':
            # Interactive stdin keeps the secret out of process arguments and shell history.
            command = shlex.join(['add-generic-password', '-U', '-s', self.service,
                                  '-a', 'api-key', '-w', key]) + '\n'
            result = self._run(['/usr/bin/security', '-i'], command)
        else:
            result = self._run(['secret-tool', 'store', '--label=Calibre book classification',
                                'service', self.service, 'account', 'api-key'], key)
        if result.returncode:
            raise CredentialError('Could not store credential')
        if self.read() != key:
            raise CredentialError('Could not verify stored credential')

    def delete(self):
        if not self.available:
            return
        if sys.platform == 'darwin':
            result = self._run(['/usr/bin/security', 'delete-generic-password', '-s', self.service, '-a', 'api-key'])
            missing = (0, 44)
        else:
            result = self._run(['secret-tool', 'clear', 'service', self.service, 'account', 'api-key'])
            missing = (0, 1)
        if result.returncode not in missing:
            raise CredentialError('Could not remove credential')
