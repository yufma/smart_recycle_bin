// Same Python API and optimizer as the local app. Each visitor owns an IndexedDB snapshot.
let py;
let cookie = '';
let snapshotId = '';
let initialSnapshot;
const STORAGE = 'inloop-public-demo-v1';
const status = text => self.postMessage({kind:'status', text});

function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(STORAGE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('state');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readSnapshot() {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('state');
      const request = tx.objectStore('state').get('server');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally { db.close(); }
}

async function writeSnapshot(snapshot) {
  const db = await database();
  try {
    await new Promise((resolve, reject) => {
      const tx = db.transaction('state', 'readwrite');
      tx.objectStore('state').put(snapshot, 'server');
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

const lock = action => navigator.locks ? navigator.locks.request(STORAGE, action) : action();

function applySnapshot(snapshot) {
  if (!snapshot || snapshot.id === snapshotId) return;
  for (const suffix of ['-wal','-shm']) {
    const path = '/inloop-data/reloop.sqlite3' + suffix;
    if (py.FS.analyzePath(path).exists) py.FS.unlink(path);
  }
  py.FS.writeFile('/inloop-data/reloop.sqlite3', snapshot.db);
  for (const [name, bytes] of Object.entries(snapshot.maps ?? {})) py.FS.writeFile('/inloop-data/maps/' + name, bytes);
  cookie = snapshot.cookie ?? '';
  snapshotId = snapshot.id;
}

async function persist() {
  py.runPython('checkpoint()');
  const maps = {};
  for (const name of py.FS.readdir('/inloop-data/maps')) {
    if (name !== '.' && name !== '..' && !name.startsWith('seed-')) maps[name] = py.FS.readFile('/inloop-data/maps/' + name);
  }
  snapshotId = crypto.randomUUID();
  await writeSnapshot({id:snapshotId, db:py.FS.readFile('/inloop-data/reloop.sqlite3'), maps, cookie});
}

const boot = async () => {
  status('체험 공간을 준비하고 있습니다. 처음 접속할 때는 잠시 걸릴 수 있어요.');
  const root = new URL('../public-demo/', self.location.href);
  // Vite passes the deployment base and source-bundle version explicitly at initialization.
  const manifest = await (await fetch(self.__init.manifest)).json();
  const archive = await (await fetch(new URL(manifest.archive + '?v=' + manifest.sha256, self.__init.manifest))).arrayBuffer();
  const {loadPyodide} = await import('https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs');
  py = await loadPyodide({indexURL:'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/'});
  status('수거 관리 기능을 준비하고 있습니다.');
  await py.loadPackage('fastapi');
  py.FS.mkdirTree('/inloop');
  py.FS.mkdirTree('/inloop-data/maps');
  py.unpackArchive(archive, 'zip', {extractDir:'/inloop'});
  py.runPython("import sys, os; sys.path.insert(0, '/inloop'); os.chdir('/inloop')");
  await lock(async () => {
    initialSnapshot = await readSnapshot();
    applySnapshot(initialSnapshot);
    status('나만의 체험 데이터를 불러오고 있습니다.');
    await py.runPythonAsync(py.FS.readFile('/inloop/browser_runtime.py', {encoding:'utf8'}));
    py.runPython('initialize_demo()');
    if (!initialSnapshot) await persist();
  });
  status('체험 준비가 끝났습니다.');
  self.postMessage({kind:'ready', hasSession:!!cookie});
};

let ready;
let queue = Promise.resolve();
self.onmessage = event => {
  const message = event.data;
  if (message.kind === 'init') {
    self.__init = message;
    ready = boot();
    ready.catch(error => { console.error(error); self.postMessage({kind:'fatal', error:'체험 환경을 불러오지 못했습니다. 인터넷 연결을 확인한 뒤 다시 시도해 주세요.'}); });
    return;
  }
  queue = queue.then(async () => {
    await ready;
    return await lock(async () => {
      const snapshot = await readSnapshot();
      applySnapshot(snapshot);
      py.globals.set('_browser_request', JSON.stringify({...message.request, cookie}));
      const result = JSON.parse(await py.runPythonAsync('await browser_request(_browser_request)'));
      const newCookie = result.headers['set-cookie'];
      if (newCookie) cookie = newCookie.split(';')[0].split('=')[1] ? newCookie.split(';')[0] : '';
      if (!['GET','HEAD'].includes(message.request.method)) await persist();
      self.postMessage({id:message.id, result, hasSession:!!cookie});
    });
  }).catch(error => { console.error(error); self.postMessage({id:message.id,error:'체험 요청을 처리하지 못했습니다. 최신 화면을 확인한 뒤 다시 시도해 주세요.'}); });
};
