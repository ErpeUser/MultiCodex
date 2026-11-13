import json
import subprocess
import unittest
from pathlib import Path


BRIDGE=Path(__file__).resolve().parents[1]/'bridge'/'service.mjs'


class RPCContract(unittest.TestCase):
    def test_bridge_rejects_unknown_method_without_secrets(self):
        proc=subprocess.run(['node',str(BRIDGE)],input=json.dumps({'id':1,'method':'passwords.dump','params':{'token':'private'}})+'\n',capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr)
        result=json.loads(proc.stdout.strip())
        self.assertEqual(result['error']['code'],'METHOD_NOT_FOUND')
        self.assertNotIn('private',proc.stdout)

    def test_bridge_health_reports_capability(self):
        proc=subprocess.run(['node',str(BRIDGE)],input=json.dumps({'id':'h','method':'health','params':{}})+'\n',capture_output=True,text=True,timeout=5)
        self.assertEqual(proc.returncode,0,proc.stderr)
        result=json.loads(proc.stdout.strip())
        self.assertEqual(result['id'],'h')
        self.assertTrue(result['result']['serviceReady'])


if __name__ == '__main__': unittest.main()
