import json
import tempfile
import threading
import runpy
import subprocess
import sys
import zipfile
import unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from companion.store import Store
from companion.engine import Engine
from local_demo import Server

class AndroidRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.saved=[]
        self.server=Server(('127.0.0.1',0),Store(Path(self.tmp.name)/'data.db'),None,
                           access_secret='test-app-secret',save_key=self.saved.append)
        self.server.engine=Engine(self.server.store,lambda p,m:'ok')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def test_bundled_runtime_survives_database_reopen(self):
        script=Path(__file__).parent/'android/scripts/bundle_runtime.py'
        bundle=runpy.run_path(str(script))['bundle']()
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(folder)
                self.assertFalse(any('.env' in n or '.sqlite' in n for n in archive.namelist()))
            code="from pathlib import Path; from companion.store import Store; p=Path('../test.db'); a=Store(p); b=Store(p); assert a.snapshot()['cards'][0]['id']==b.snapshot()['cards'][0]['id']"
            result=subprocess.run([sys.executable,'-c',code],cwd=Path(folder)/'client',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_bootstrap_requires_native_cookie(self):
        for path in ['/','/api/bootstrap','/app.js']:
            with self.assertRaises(HTTPError) as e:urlopen(self.url+path)
            self.assertEqual(e.exception.code,403)
        req=Request(self.url+'/api/bootstrap',headers={'Cookie':'qiyu_access=test-app-secret'})
        with urlopen(req) as r:data=json.load(r)
        self.assertTrue(data['secure_key_storage'])
        self.assertNotIn('api_key',data)
    def test_key_saved_only_through_authenticated_request(self):
        data=json.dumps({'api_key':'synthetic-test-key','model':'deepseek-flash'}).encode()
        headers={'Cookie':'qiyu_access=test-app-secret','X-Local-Token':self.server.token,'Content-Type':'application/json'}
        with urlopen(Request(self.url+'/api/settings',data=data,headers=headers)) as r:self.assertTrue(json.load(r)['ready'])
        self.assertEqual(self.saved,['synthetic-test-key'])
        self.assertNotIn('synthetic-test-key',json.dumps(self.server.store.export()))
        headers['Cookie']='qiyu_access=wrong'
        with self.assertRaises(HTTPError):urlopen(Request(self.url+'/api/settings',data=data,headers=headers))
        self.assertEqual(len(self.saved),1)
if __name__=='__main__':unittest.main()
