import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
const script = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'service.mjs');
function call(method, params={}) {
  const proc = spawnSync(process.execPath, [script], {
    input: JSON.stringify({id: 1, method, params})+'\n', encoding:'utf8', timeout:5000
  });
  assert.equal(proc.status, 0, proc.stderr);
  return JSON.parse(proc.stdout);
}
test('health is available without provider access', () => {
  assert.equal(call('health').result.protocol, 1);
});
test('unknown method never repeats user input', () => {
  const secret='sensitive-user-supplied-secret';
  const response = call('missing.method', {token:secret});
  assert.equal(response.error.code, 'METHOD_NOT_FOUND');
  assert.ok(!JSON.stringify(response).includes(secret));
});
test('invalid index rejects before accessing storage', () => {
  assert.equal(call('accounts.switch', {index:0}).error.code, 'BAD_PARAMS');
});

test('malformed request shape returns BAD_PARAMS, not a raw TypeError', () => {
  const proc = spawnSync(process.execPath,[script],{input:'null\n',encoding:'utf8'});
  assert.equal(JSON.parse(proc.stdout).error.code,'BAD_PARAMS');
});
test('health distinguishes a running service from a ready upstream', () => {
  const result = call('health').result;
  assert.equal(typeof result.upstreamReady,'boolean');
  assert.equal(typeof result.nodeCompatible,'boolean');
});
test('invalid global switch does not write account storage', () => {
  assert.equal(call('accounts.switch',{index:1}).error.code,'UNSAFE_GLOBAL_SWITCH');
});

import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, readdirSync, rmSync, copyFileSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
function withStore(data, work) {
  const base=tmpdir();
  // Some hermetic Linux runners do not pre-create /tmp. Node's tmpdir()
  // contract returns the path, but does not promise that it already exists.
  mkdirSync(base,{recursive:true});
  const root=mkdtempSync(join(base,'multicodex-contract-'));
  try {
    const module=join(root,'node_modules','codex-multi-auth'); mkdirSync(module,{recursive:true});
    writeFileSync(join(module,'package.json'),JSON.stringify({name:'codex-multi-auth',version:'2.26.0',type:'module',exports:{'./package.json':'./package.json','./storage':'./storage.mjs'}}));
    writeFileSync(join(module,'storage.mjs'), 'export function getStoragePath(){return process.env.MULTICODEX_TEST_STORE} export function loadAccounts(){throw Error("Do not migrate or repair during inventory")}');
    const store=join(root,'accounts.json');writeFileSync(store,JSON.stringify(data));
    const service=join(root,'service.mjs');copyFileSync(script,service);
    const invoke = () => spawnSync(process.execPath,[service],{input:JSON.stringify({id:7,method:'accounts.list',params:{}})+'\n',encoding:'utf8',timeout:5000,env:{...process.env,MULTICODEX_TEST_STORE:store}});
    work({root,store,invoke});
  } finally {rmSync(root,{recursive:true,force:true});}
}
test('inventory strips all credentials and leaves source bytes and files unchanged', () => {
  withStore({version:3,activeIndex:0,accounts:[{email:'test@example.invalid',accountLabel:'Work',accessToken:'TOKEN-FIXTURE',refreshToken:'REFRESH-FIXTURE',enabled:true}]}, ({root,store,invoke}) => {
    const original=readFileSync(store);const files=readdirSync(root);
    const proc=invoke();assert.equal(proc.status,0);
    const body=JSON.parse(proc.stdout);
    assert.equal(body.result.accounts[0].email,'test@example.invalid');
    assert.equal(body.result.verification,'stored-only');
    assert.ok(!proc.stdout.includes('TOKEN-FIXTURE'));assert.ok(!proc.stdout.includes('REFRESH-FIXTURE'));
    assert.deepEqual(readFileSync(store),original);assert.deepEqual(readdirSync(root),files);
  });
});
test('unsupported source schema fails closed and remains byte-identical', () => {
  withStore({version:99,accounts:[],secret:'FIXTURE'}, ({store,invoke}) => {
    const original=readFileSync(store);const proc=invoke();
    assert.equal(JSON.parse(proc.stdout).error.code,'STORAGE_INVALID');
    assert.deepEqual(readFileSync(store),original);
    assert.ok(!proc.stdout.includes('FIXTURE'));
  });
});
test('redirected source file is rejected instead of following an unexpected path', t => {
  withStore({version:3,accounts:[]}, ({root,store,invoke}) => {
    const target=join(root,'foreign.json');writeFileSync(target,'{"version":3,"accounts":[]}');
    rmSync(store);
    try {symlinkSync(target,store);} catch {t.skip('Host does not permit symlinks');return;}
    assert.equal(JSON.parse(invoke().stdout).error.code,'STORAGE_INVALID');
  });
});

test('inventory emits bounded well-formed text without changing source', () => {
  const cases = [
    ['controls', 'A\nB\u007f', 'AB'],
    ['ASCII cap', 'X'.repeat(161), 'X'.repeat(160)],
    ['complete pair', 'X'.repeat(158)+'\u{1f600}', 'X'.repeat(158)+'\u{1f600}'],
    ['split pair', 'X'.repeat(159)+'\u{1f600}', 'X'.repeat(159)],
    ['lone surrogates', '\ud800A\udc00', 'A']
  ];
  for (const [name, value, expected] of cases) {
    const record={accountLabel:value,email:value,recordId:value,
      refreshToken:'UNICODE-TOKEN-FIXTURE',addedAt:1,lastUsed:1};
    withStore({version:3,activeIndex:0,accounts:[record]}, ({store,invoke}) => {
      const original=readFileSync(store);const proc=invoke();assert.equal(proc.status,0,name);
      const row=JSON.parse(proc.stdout).result.accounts[0];
      for (const field of ['label','email','recordId']) {
        assert.equal(row[field],expected,`${name}: ${field}`);
        assert.ok(row[field].isWellFormed(),`${name}: ${field}`);
        assert.ok(row[field].length<=160,`${name}: ${field}`);
      }
      assert.deepEqual(readFileSync(store),original);
      assert.ok(!proc.stdout.includes('UNICODE-TOKEN-FIXTURE'));
    });
  }
});
