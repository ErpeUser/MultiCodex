"""Scripted stdio peer for transport tests, not a provider/login simulation claim."""
import json
import os
import sys
import time
mode = os.environ.get('MULTICODEX_FIXTURE_MODE', '')
for line in sys.stdin:
    req = json.loads(line)
    if 'id' not in req:
        continue
    method = req.get('method')
    if mode == 'hang' and method == 'account/read':
        time.sleep(2); continue
    if mode == 'secret-error' and method == 'account/read':
        print(json.dumps({'id':req['id'],'error':{'code':-1,'message':'fixture-secret-never-display'}}), flush=True)
        continue
    if mode == 'oversized' and method == 'account/read':
        print('x'*1_100_000, flush=True); continue
    result = {}
    if method == 'account/read':
        result = {'account':{'type':'chatgpt','email':'test@example.invalid','planType':'plus'}}
    if method == 'account/login/start':
        result = {'type':'chatgpt','loginId':'fixture-login','authUrl':'https://auth.openai.com/authorize?fixture=1'}
        # A valid server may send completion before the start-response reaches the reader.
        print(json.dumps({'method':'account/login/completed','params':{'loginId':'fixture-login','success':True}}), flush=True)
    print(json.dumps({'id':req['id'],'result':result}), flush=True)
