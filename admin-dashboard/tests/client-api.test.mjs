import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

// Execute the real client helper without a browser or additional test dependencies.
const compiled = ts.transpileModule(readFileSync(new URL('../src/types.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function client(fetch) {
  let expire;
  let cleared = false;
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, fetch, AbortController, Error, TypeError, Intl,
    window: {
      setTimeout(callback, delay) { assert.equal(delay, 30000); expire = callback; return 1; },
      clearTimeout(id) { assert.equal(id, 1); cleared = true; },
    },
  });
  return { api: exports.api, expire: () => expire(), cleared: () => cleared };
}

test('successful writes retain their method, body and same-origin credentials', async () => {
  const c = client(async (url, options) => {
    assert.equal(url, '/api/plan');
    assert.equal(options.method, 'POST');
    assert.equal(options.body, '{"include_orange":true}');
    assert.equal(options.credentials, 'same-origin');
    return { ok: true, json: async () => ({ saved: true }) };
  });
  assert.equal((await c.api('/plan', { method: 'POST', body: '{"include_orange":true}' })).saved, true);
  assert.equal(c.cleared(), true);
});

test('server validation details remain available to the persistent error notice', async () => {
  const c = client(async () => ({ ok: false, status: 422, json: async () => ({ detail: '주의 기준은 수거 기준보다 낮아야 합니다.' }) }));
  await assert.rejects(c.api('/config'), error => error.status === 422 && error.message.includes('주의 기준'));
  assert.equal(c.cleared(), true);
});

test('expired sessions retain status 401 so the app can return to login', async () => {
  const c = client(async () => ({ ok: false, status: 401, json: async () => ({ detail: '로그인이 필요합니다.' }) }));
  await assert.rejects(c.api('/workspace'), error => error.status === 401);
});

test('a network failure explains how to reconnect', async () => {
  const c = client(async () => { throw new TypeError('Failed to fetch'); });
  await assert.rejects(c.api('/workspace'), /서버 실행 상태를 확인/);
  assert.equal(c.cleared(), true);
});

test('a timeout releases the pending request and never retries a write', async () => {
  let attempts = 0;
  const c = client(async (_url, options) => {
    attempts++;
    return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(Object.assign(new Error(), { name: 'AbortError' }))));
  });
  const pending = c.api('/collect/B-002', { method: 'POST' });
  c.expire();
  await assert.rejects(pending, /작업 반영 여부를 확인/);
  assert.equal(attempts, 1);
  assert.equal(c.cleared(), true);
});

test('non-JSON errors still provide an actionable message', async () => {
  const c = client(async () => ({ ok: false, status: 500, json: async () => { throw new Error('Not JSON'); } }));
  await assert.rejects(c.api('/plan'), error => error.status === 500 && error.message.includes('다시 시도'));
});
