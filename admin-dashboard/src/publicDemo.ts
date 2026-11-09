import type { WorkspaceResponse } from './types';

type Reply = { status: number; headers: Record<string,string>; body: string };
const images = new Map<string,string>();
let worker: Worker | null = null;
let sequence = 0;
const waiting = new Map<number,{ resolve: (reply: Reply) => void; reject: (error: Error) => void }>();
const error = (message: string, status = 500) => Object.assign(new Error(message), {status});

function ensureWorker() {
  if (worker) return worker;
  worker = new Worker(new URL('./publicDemoWorker.js', import.meta.url), {type:'module'});
  worker.onmessage = event => {
    const message = event.data;
    if (message.kind === 'status') {
      window.inloopDemoStatus = message.text;
      window.dispatchEvent(new CustomEvent('inloop-demo-status', {detail:message.text}));
      return;
    }
    if (message.hasSession !== undefined) localStorage.setItem('inloop-demo-session', message.hasSession ? 'yes' : 'no');
    if (message.kind === 'fatal') {
      window.inloopDemoStatus = message.error;
      window.dispatchEvent(new CustomEvent('inloop-demo-status', {detail:message.error}));
      for (const request of waiting.values()) request.reject(error(message.error));
      waiting.clear(); worker?.terminate(); worker = null; return;
    }
    const request = waiting.get(message.id);
    if (!request) return;
    waiting.delete(message.id);
    if (message.error) request.reject(error(message.error)); else request.resolve(message.result);
  };
  worker.onerror = () => {
    for (const request of waiting.values()) request.reject(error('체험 환경 연결이 중단됐습니다. 화면을 새로고침해 주세요.'));
    waiting.clear(); worker?.terminate(); worker = null;
  };
  worker.postMessage({kind:'init', manifest:new URL(import.meta.env.BASE_URL + 'public-demo/manifest.json', location.origin).href});
  return worker;
}

function request(path: string, options: RequestInit = {}): Promise<Reply> {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    waiting.set(id, {resolve,reject});
    const headers = Object.fromEntries(new Headers(options.headers).entries());
    ensureWorker().postMessage({id, request:{path, method:options.method ?? 'GET', headers, body:typeof options.body === 'string' ? options.body : ''}});
  });
}

const bytes = (reply: Reply) => Uint8Array.from(atob(reply.body), character => character.charCodeAt(0));
const decode = (reply: Reply) => JSON.parse(new TextDecoder().decode(bytes(reply)));

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (path === '/workspace' && !localStorage.getItem('inloop-demo-session')?.includes('yes')) {
    throw error('체험 계정으로 시작해 주세요.', 401);
  }
  const reply = await request(path, options);
  const result = decode(reply);
  if (reply.status >= 400) throw error(typeof result.detail === 'string' ? result.detail : '입력값을 확인해 주세요.', reply.status);
  const workspace = result as WorkspaceResponse;
  if (workspace.building && 'map_images' in workspace) {
    workspace.map_image_urls = {};
    for (const [floor,name] of Object.entries(workspace.map_images)) {
      if (!images.has(name)) {
        const photo = await request(`/floorplan/${floor}?building_id=${workspace.workspace_id}`);
        if (photo.status === 200) images.set(name, URL.createObjectURL(new Blob([bytes(photo)],{type:photo.headers['content-type'] ?? 'image/jpeg'})));
      }
      workspace.map_image_urls[floor] = images.get(name) ?? '';
    }
  }
  return result as T;
}

export function installPublicDemo() {
  window.inloopPublicDemo = true;
  document.documentElement.dataset.publicDemo = 'true';
  window.inloopDemoApi = api;
  ensureWorker();
}
