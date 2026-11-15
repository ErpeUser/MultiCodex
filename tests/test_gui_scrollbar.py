"""A page scroll notification must not reenter CustomTkinter's idle drawing."""
import json
import subprocess
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows GUI regression')
class GuiScrollbarTests(unittest.TestCase):
    def test_all_pages_and_themes_settle_without_recursive_scrollbar_draw(self):
        script = '''
import json
from multicodex.gui_check import check_gui
print(json.dumps(check_gui()), flush=True)
'''
        try:
            run = subprocess.run([sys.executable, '-c', script],
                                 cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            self.fail('Page/theme changes must settle without recursive scrollbar drawing')
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertTrue(result['ready'])
        self.assertEqual(len(result['screens']), 12)
