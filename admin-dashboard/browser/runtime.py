"""Run the unchanged application API inside a single browser worker, with no network server."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import anyio.to_thread


# Pyodide's standard library omits OpenSSL's PBKDF2 helper. Keep the same SHA-256
# algorithm and iteration count as the local server using portable HMAC primitives.
if not hasattr(hashlib, 'pbkdf2_hmac'):
    def portable_pbkdf2(name, password, salt, iterations, dklen=None):
        template = hmac.new(password, digestmod=name)
        size = template.digest_size
        output = b''
        for block in range(1, ((dklen or size) + size - 1) // size + 1):
            first = template.copy()
            first.update(salt + block.to_bytes(4, 'big'))
            u = first.digest()
            total = int.from_bytes(u, 'big')
            for _ in range(iterations - 1):
                step = template.copy()
                step.update(u)
                u = step.digest()
                total ^= int.from_bytes(u, 'big')
            output += total.to_bytes(size, 'big')
        return output[:dklen or size]
    hashlib.pbkdf2_hmac = portable_pbkdf2


async def run_in_worker(func, *args, **kwargs):
    # The browser worker already isolates this work from the page. Emscripten cannot
    # create the extra OS threads used by a conventional ASGI thread pool.
    return func(*args)


anyio.to_thread.run_sync = run_in_worker
os.environ['RELOOP_DATA_DIR'] = '/inloop-data'
from server import app as backend


def seed_account(user_id):
    with backend.database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS public_demo_seeded_accounts(user_id INTEGER PRIMARY KEY REFERENCES users(id))')
        if db.execute('SELECT 1 FROM public_demo_seeded_accounts WHERE user_id=?', (user_id,)).fetchone():
            return
        seeds = json.loads(Path('/inloop/demo-assets/seeds.json').read_text())
        first = backend.building_store.selected(db, user_id)
        for i, state in enumerate(seeds):
            for bin in state['bins']:
                if bin.get('measured_at'):
                    bin.update(measured_at=backend.now(), received_at=backend.now())
            if i == 0 and first:
                db.execute('UPDATE buildings SET state_json=? WHERE id=? AND user_id=?',
                           (json.dumps(state, ensure_ascii=False), first, user_id))
            else:
                new_id = backend.building_store.create(db, user_id, state, backend.now())
                if not first:
                    first = new_id
        backend.building_store.choose(db, user_id, first)
        db.execute('INSERT INTO public_demo_seeded_accounts(user_id) VALUES(?)', (user_id,))


def initialize_demo():
    backend.init_db()
    for path in Path('/inloop/demo-assets').glob('seed-*'):
        target = backend.MAP_DIR / path.name
        if not target.exists():
            shutil.copyfile(path, target)
    with backend.database() as db:
        user_id = db.execute('SELECT id FROM users WHERE email=?', (backend.DEMO_EMAIL,)).fetchone()[0]
    seed_account(user_id)


def checkpoint():
    with backend.database() as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')


async def browser_request(raw):
    request = json.loads(raw)
    parts = urlsplit(request['path'])
    path = '/api' + parts.path
    if parts.path in ('/device/key', '/device/readings'):
        return json.dumps({'status': 403, 'headers': {'content-type': 'application/json'},
                           'body': base64.b64encode(json.dumps({'detail': '공개 체험에서는 실물 연결 대신 시뮬레이션을 사용해 주세요.'}).encode()).decode()})
    payload = request.get('body', '').encode()
    headers = [(str(k).lower().encode(), str(v).encode()) for k, v in request.get('headers', {}).items()]
    headers += [(b'host', b'inloop-demo.local'), (b'content-type', b'application/json'),
                (b'content-length', str(len(payload)).encode())]
    if request.get('cookie'):
        headers.append((b'cookie', request['cookie'].encode()))
    messages = []
    done = asyncio.Event()
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {'type': 'http.request', 'body': payload, 'more_body': False}
        await done.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        messages.append(message)
        if message['type'] == 'http.response.body' and not message.get('more_body', False):
            done.set()

    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'}, 'http_version': '1.1',
             'method': request.get('method', 'GET'), 'path': path, 'raw_path': path.encode(),
             'query_string': parts.query.encode(), 'root_path': '', 'headers': headers,
             'server': ('inloop-demo.local', 80), 'scheme': 'http', 'client': ('127.0.0.1', 1)}
    await backend.app(scope, receive, send)
    start = next(m for m in messages if m['type'] == 'http.response.start')
    body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    response_headers = {k.decode(): v.decode() for k, v in start.get('headers', [])}
    if parts.path == '/auth/register' and start['status'] == 201:
        seed_account(json.loads(body)['id'])
    return json.dumps({'status': start['status'], 'headers': response_headers,
                       'body': base64.b64encode(body).decode()})
