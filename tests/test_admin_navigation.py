"""Execute the original navigation methods without a third-party GUI backend.

This is a boundary test, not full CustomTkinter/Windows acceptance.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


def method(name):
    path=Path(__file__).resolve().parents[1]/'multicodex'/'gui.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MultiCodexApp')
    node=next((n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
    if node is None:raise AssertionError('Navigation method is missing: '+name)
    code=ast.Module(body=[node],type_ignores=[]);ast.fix_missing_locations(code)
    ns={};exec(compile(code,str(path),'exec'),ns);return ns[name]


class AdminNavigationTests(unittest.TestCase):
    def host(self):
        events=[]
        host=SimpleNamespace(closing=False,account_section='workspace',login_cancel=None,
            view={'profiles':[],'sessions':{},'recovery':{}},pool_rows=None,pool_error=None,
            _panel=lambda *a:object(),_line=lambda *a,**k:None,_actions=lambda *a:None,
            _new_profile=lambda:None,_set_account_section=lambda *a:None,
            _set_page=lambda page:events.append(page),admin=SimpleNamespace(render=lambda:events.append('admin')))
        return host,events
    def test_workspace_subview_renders_admin_not_profile_forms(self):
        host,events=self.host();method('_page_accounts')(host)
        self.assertEqual(events,['admin'])
    def test_subview_switch_returns_to_accounts(self):
        host,events=self.host();method('_set_account_section')(host,'profiles')
        self.assertEqual(host.account_section,'profiles');self.assertEqual(events,['Accounts'])
    def test_invalid_subview_is_ignored(self):
        host,events=self.host();method('_set_account_section')(host,'arbitrary')
        self.assertEqual(host.account_section,'workspace');self.assertEqual(events,[])
    def test_closed_app_does_not_navigate(self):
        host,events=self.host();host.closing=True;method('_set_account_section')(host,'profiles')
        self.assertEqual(events,[])

if __name__=='__main__':unittest.main()
