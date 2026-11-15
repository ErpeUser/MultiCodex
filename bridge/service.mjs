/** Metadata-only direct integration with the published storage facade.
 * Never invoke manager CLI commands: even status can run first-use migrations.
 * Source files are read only. No global pin, refresh, repair or token export.
 */
import { open, lstat } from 'node:fs/promises';
import { constants } from 'node:fs';
import { dirname, join } from 'node:path';
const MAX_INPUT = 65536;
const MAX_STORE = 8 * 1024 * 1024;
const MESSAGES = Object.freeze({
  BAD_PARAMS: 'Invalid request', METHOD_NOT_FOUND: 'Unknown RPC method',
  UPSTREAM_UNAVAILABLE: 'Account manager package is unavailable',
  UPSTREAM_VERSION: 'Unsupported account manager version',
  STORAGE_INVALID: 'Saved account data is unreadable or unsupported',
  UNSAFE_GLOBAL_SWITCH: 'Global pinning cannot change an isolated desktop session',
  INTERNAL: 'Account operation failed'
});
class SafeError extends Error {
  constructor(code) { super(MESSAGES[code]); this.code = code; }
}
const fail = code => { throw new SafeError(code); };
const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
// Unicode mode removes lone surrogates after truncation, retaining complete pairs.
const label = x => typeof x === 'string' ? x.replace(/[\x00-\x1f\x7f]/g, '').slice(0, 160).replace(/[\uD800-\uDFFF]/gu, '') : null;
const nodeCompatible = (() => {
  const [major, minor] = process.versions.node.split('.').map(Number);
  return major > 22 || (major === 22 && minor >= 19);
})();
async function facade() {
  try {
    const meta = await import('codex-multi-auth/package.json', {with:{type:'json'}});
    if (meta.default.version !== '2.26.0') fail('UPSTREAM_VERSION');
    const api = await import('codex-multi-auth/storage');
    if (typeof api.getStoragePath !== 'function') fail('UPSTREAM_VERSION');
    return api;
  } catch (e) { if (e instanceof SafeError) throw e; fail('UPSTREAM_UNAVAILABLE'); }
}
async function readJSON(path) {
  let file;
  try {
    const original = await lstat(path);
    if (!original.isFile() || original.isSymbolicLink()) fail('STORAGE_INVALID');
    file = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
    const info = await file.stat();
    if (!info.isFile() || info.size > MAX_STORE || info.dev !== original.dev || info.ino !== original.ino) fail('STORAGE_INVALID');
    // Bound the actual bytes read as well as the initial stat: a concurrently
    // growing file must not turn this metadata request into an unbounded read.
    const buffer = Buffer.alloc(Math.min(info.size + 1, MAX_STORE + 1));
    let size = 0;
    while (size < buffer.length) {
      const read = await file.read(buffer, size, buffer.length - size, size);
      if (read.bytesRead === 0) break;
      size += read.bytesRead;
    }
    const after = await file.stat();
    if (size !== info.size || after.size !== info.size || after.mtimeMs !== info.mtimeMs) fail('STORAGE_INVALID');
    return JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(buffer.subarray(0,size)));
  } catch (e) {
    if (e?.code === 'ENOENT') return null;
    if (e instanceof SafeError) throw e;
    fail('STORAGE_INVALID');
  } finally {
    if (file) await file.close();
  }
}

function inventory(data) {
  if (data === null) return {accounts:[],count:0,source:'multi-auth',verification:'stored-only'};
  if (!object(data) || data.version !== 3 || !Array.isArray(data.accounts) ||
      data.accounts.length > 1000 || data.accounts.some(a => !object(a))) fail('STORAGE_INVALID');
  const accounts = data.accounts.map((a,i) => ({
    index:i+1, label:label(a.accountLabel), email:label(a.email), recordId:label(a.recordId),
    enabled:a.enabled!==false, invalidated:Number.isFinite(a.authInvalidatedAt),
    active:i===data.activeIndex, pinned:i===data.pinnedAccountIndex,
    verification:'stored-only',
    expired:Number.isFinite(a.expiresAt) ? a.expiresAt <= Date.now() : null
  }));
  return {accounts,count:accounts.length,source:'multi-auth',verification:'stored-only'};
}
async function run(method, params) {
  if (method === 'health') {
    let upstreamReady=false;
    try { await facade(); upstreamReady=true; } catch { /* Metadata-only health. */ }
    return {serviceReady:true,protocol:1,nodeCompatible,upstreamReady,
      ready:nodeCompatible && upstreamReady, requiredUpstream:'2.26.0'};
  }
  if (method === 'accounts.switch') {
    if (!Number.isSafeInteger(params.index) || params.index < 1) fail('BAD_PARAMS');
    fail('UNSAFE_GLOBAL_SWITCH');
  }
  if (!['accounts.list','accounts.limits'].includes(method)) fail('METHOD_NOT_FOUND');
  const api = await facade();
  const path = api.getStoragePath();
  if (typeof path !== 'string' || !path) fail('STORAGE_INVALID');
  if (method === 'accounts.list') return inventory(await readJSON(path));
  // Do not pass unversioned cache/provider JSON through to the UI. Live limits
  // for managed sessions are obtained via official account/rateLimits/read.
  const cache = await readJSON(join(dirname(path),'quota-cache.json'));
  return {available:false,source:'multi-auth-cache',cachePresent:cache!==null,
    reason:'Use managed-session limits; this cache schema is not a stable public API'};
}
async function respond(line) {
  let id=null;
  try {
    const request=JSON.parse(line);
    if (!object(request)) fail('BAD_PARAMS');
    if (Number.isSafeInteger(request.id) || (typeof request.id==='string' && /^[A-Za-z0-9_-]{1,64}$/.test(request.id))) id=request.id;
    else fail('BAD_PARAMS');
    if (typeof request.method!=='string' || (request.params!==undefined && !object(request.params))) fail('BAD_PARAMS');
    const result=await run(request.method,request.params||{});
    process.stdout.write(JSON.stringify({id,result})+'\n');
  } catch (e) {
    const code=e instanceof SafeError ? e.code : (e instanceof SyntaxError ? 'BAD_PARAMS' : 'INTERNAL');
    process.stdout.write(JSON.stringify({id,error:{code,message:MESSAGES[code]}})+'\n');
  }
}
// Bound input before assembling a potentially enormous line. Process one line
// at a time so writes and responses cannot race; stdout is protocol-only.
let pending=Buffer.alloc(0);
for await (const chunk of process.stdin) {
  pending=Buffer.concat([pending,chunk]);
  let end;
  while ((end=pending.indexOf(10))!==-1) {
    if (end>MAX_INPUT) { await respond('{}'); process.exitCode=1; break; }
    const line=pending.subarray(0,end).toString('utf8');pending=pending.subarray(end+1);
    await respond(line);
  }
  if (pending.length>MAX_INPUT || process.exitCode) { process.stdin.destroy(); break; }
}
if (pending.length && pending.length<=MAX_INPUT && !process.exitCode) await respond(pending.toString('utf8'));
