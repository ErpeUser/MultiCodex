import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from multicodex.processes import PsutilPlatform, ProcessSafetyError
from multicodex.profiles import validate_name, ProfileError

class VisibilityTests(unittest.TestCase):
    def test_inaccessible_candidate_is_unknown_not_silently_absent(self):
        process=SimpleNamespace(info={'name':'ChatGPT.exe','exe':None,'cmdline':None},is_running=lambda:True)
        with patch('psutil.process_iter',return_value=[process]):
            with self.assertRaises(ProcessSafetyError):PsutilPlatform().list_processes()

    def test_missing_candidate_command_line_blocks_safe_identity_claim(self):
        process=SimpleNamespace(info={'name':'ChatGPT.exe','exe':str(Path('/tmp')/'OpenAI.Codex_fixture'/'app'/'ChatGPT.exe'),'cmdline':None},is_running=lambda:True,create_time=lambda:123,pid=44)
        with patch('psutil.process_iter',return_value=[process]):
            with self.assertRaises(ProcessSafetyError):PsutilPlatform().list_processes()

    def test_hidden_profile_name_is_rejected_not_created_then_hidden(self):
        with self.assertRaises(ProfileError):validate_name('.Hidden')
