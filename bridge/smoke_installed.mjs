/** Exercise the actual installed storage export with isolated synthetic state.
 * No upstream CLI, migration, installation hook, network or real account is used.
 * Run with the bundled node.exe and runtime directory after npm --ignore-scripts.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

let scratch;
try {
  const runtime = resolve(process.argv[2] || 'bridge');
  scratch = mkdtempSync(join(tmpdir(), 'multicodex-storage-smoke-'));
  const home = join(scratch, 'home');
  const storage = join(scratch, 'storage');
  mkdirSync(home); mkdirSync(storage);
  // Set overrides before importing any upstream module. Assertions below ensure
  // a future upstream version cannot silently escape this isolated fixture.
  const env = { ...process.env, HOME: home, USERPROFILE: home,
    CODEX_HOME: join(home, '.codex'), CODEX_MULTI_AUTH_DIR: storage,
    XDG_CONFIG_HOME: join(home, '.config'), APPDATA: join(home, 'AppData'),
    LOCALAPPDATA: join(home, 'LocalAppData') };
  Object.assign(process.env, env);
  const require = createRequire(pathToFileURL(join(runtime, 'service.mjs')));
  const metadata = JSON.parse(readFileSync(require.resolve('codex-multi-auth/package.json'), 'utf8'));
  assert.equal(metadata.version, '2.26.0');
  const api = await import(pathToFileURL(require.resolve('codex-multi-auth/storage')));
  assert.equal(typeof api.getStoragePath, 'function');
  const path = api.getStoragePath();
  assert.equal(typeof path, 'string');
  const inside = relative(scratch, resolve(path));
  assert.ok(inside && !inside.startsWith('..' + sep) && inside !== '..' && !isAbsolute(inside));
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify({version: 3, activeIndex: 0, accounts: [{
    email: 'fixture@example.invalid', accountLabel: 'Smoke fixture',
    accessToken: 'ACCESS-SYNTHETIC-SMOKE', refreshToken: 'REFRESH-SYNTHETIC-SMOKE',
    idToken: 'ID-SYNTHETIC-SMOKE', enabled: true }] }));
  function snapshot(directory) {
    const result = {};
    function walk(current) {
      for (const entry of readdirSync(current)) {
        const item = join(current, entry);
        if (statSync(item).isDirectory()) walk(item);
        else result[relative(directory, item)] = createHash('sha256').update(readFileSync(item)).digest('hex');
      }
    }
    walk(directory); return result;
  }
  const before = snapshot(scratch);
  const result = spawnSync(process.execPath, [join(runtime, 'service.mjs')], {
    env, cwd: scratch, encoding: 'utf8', timeout: 15000,
    input: JSON.stringify({ id: 1, method: 'health', params: {} }) + '\n' +
           JSON.stringify({ id: 2, method: 'accounts.list', params: {} }) + '\n'
  });
  assert.equal(result.status, 0);
  assert.equal(result.stderr, '');
  const responses = result.stdout.trim().split('\n').map(line => JSON.parse(line));
  assert.equal(responses.length, 2);
  assert.equal(responses[0].result.ready, true);
  assert.equal(responses[1].result.count, 1);
  assert.equal(responses[1].result.accounts[0].email, 'fixture@example.invalid');
  assert.equal(responses[1].result.verification, 'stored-only');
  for (const secret of ['ACCESS-SYNTHETIC-SMOKE', 'REFRESH-SYNTHETIC-SMOKE', 'ID-SYNTHETIC-SMOKE']) {
    assert.ok(!result.stdout.includes(secret));
  }
  assert.deepEqual(snapshot(scratch), before);
  process.stdout.write(JSON.stringify({ready: true, upstream: metadata.version,
    node: process.versions.node, storageExport: true, inventoryReadOnly: true,
    credentialsRedacted: true, scope: 'synthetic installed-package smoke; not OAuth/native acceptance'}) + '\n');
} catch {
  process.stdout.write(JSON.stringify({ready: false, error: 'INSTALLED_STORAGE_SMOKE_FAILED'}) + '\n');
  process.exitCode = 1;
} finally {
  if (scratch) rmSync(scratch, {recursive: true, force: true});
}
