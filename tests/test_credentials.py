import importlib.util
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('jev_credentials_test', Path(__file__).resolve().parents[1] / 'plugin/credentials.py')
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


class CredentialTests(unittest.TestCase):
    def test_profiles_have_distinct_vault_entries(self):
        self.assertNotEqual(credentials.CredentialStore('/profile-one').service,
                            credentials.CredentialStore('/profile-two').service)

    def test_macos_write_passes_secret_on_stdin_not_arguments(self):
        store = credentials.CredentialStore('/test-only-profile')
        key = 'synthetic-key-never-transmitted'
        replies = [subprocess.CompletedProcess([], 0, ''), subprocess.CompletedProcess([], 0, key + '\n')]
        with patch.object(credentials.sys, 'platform', 'darwin'), patch.object(credentials.subprocess, 'run', side_effect=replies) as run:
            store.write(key)
        call = run.call_args_list[0]
        self.assertEqual(call.args[0], ['/usr/bin/security', '-i'])
        self.assertNotIn(key, repr(call.args[0]))
        self.assertIn(key, call.kwargs['input'])
        self.assertEqual(call.kwargs['stderr'], subprocess.DEVNULL)

    def test_write_failure_does_not_expose_secret(self):
        store = credentials.CredentialStore('/test-only-profile')
        with patch.object(credentials.sys, 'platform', 'darwin'), patch.object(credentials.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '')):
            with self.assertRaises(credentials.CredentialError) as caught:
                store.write('private-synthetic-key')
        self.assertNotIn('private-synthetic-key', str(caught.exception))

    def test_missing_key_is_empty_and_delete_is_idempotent(self):
        store = credentials.CredentialStore('/test-only-profile')
        with patch.object(credentials.sys, 'platform', 'darwin'), patch.object(credentials.subprocess, 'run', return_value=subprocess.CompletedProcess([], 44, '')):
            self.assertEqual(store.read(), '')
            store.delete()

    def test_linux_unavailable_does_not_fall_back_to_plaintext(self):
        store = credentials.CredentialStore('/test-only-profile')
        with patch.object(credentials.sys, 'platform', 'linux'), patch.object(credentials.shutil, 'which', return_value=None):
            self.assertFalse(store.available)
            self.assertEqual(store.read(), '')
            with self.assertRaises(credentials.CredentialError):
                store.write('synthetic-key')
