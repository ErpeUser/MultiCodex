"""Compiler versions come from ISPP, including compilers with empty PE versions."""
from pathlib import Path
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from tools.compiler_identity import compiler_version


class CompilerIdentityTests(unittest.TestCase):
    def test_missing_or_ambiguous_version_is_rejected(self):
        for output in ('', 'Compiler 6.7.3', 'MULTICODEX_INNO_VERSION=6.7.3\nMULTICODEX_INNO_VERSION=6.7.1'):
            with self.subTest(output=output), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                with self.assertRaises(ValueError):
                    compiler_version(Path('ISCC.exe'))

    def test_failed_compilation_cannot_claim_version(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, 'MULTICODEX_INNO_VERSION=6.7.3', 'error')):
            with self.assertRaises(ValueError):
                compiler_version(Path('ISCC.exe'))

    @unittest.skipUnless(sys.platform == 'win32', 'Native Inno compiler required')
    def test_real_installed_compiler_answers_without_creating_setup(self):
        compiler = Path(os.environ['LOCALAPPDATA']) / 'Programs/Inno Setup 6/ISCC.exe'
        if not compiler.is_file():
            self.skipTest('Inno Setup is not installed in the user compiler path')
        self.assertRegex(compiler_version(compiler), r'^\d+\.\d+\.\d+$')
