export type Page = 'dashboard' | 'map' | 'team' | 'history' | 'device' | 'settings';
export type Status = 'normal' | 'warning' | 'critical' | 'offline' | 'pending';
export type RouteMode = 'fastest' | 'lean';
export interface User { id: number; name: string; email: string }
export interface Building {
  name: string; floors: number; total_staff: number; available_staff: number;
  include_orange: boolean; route_mode?: RouteMode; office_floor: number; office_x: number; office_y: number;
  office_access_node: string; meters_per_unit: number; speed_mps: number;
  service_seconds: number; warning_threshold: number; critical_threshold: number; stale_minutes: number;
  stairs_up_seconds?: number; stairs_down_seconds?: number; elevator_wait_seconds?: number; elevator_floor_seconds?: number;
  use_cart?: boolean; cart_capacity?: number; depot_node?: string; unload_seconds?: number; max_work_minutes?: number;
}
export interface Bin {
  id: string; name: string; floor: number; x: number; y: number; access_node: string;
  category: string; fill: number | null; device_type: 'real' | 'demo';
  reading_source: 'actual' | 'simulated' | 'demo' | 'unconnected';
  measured_at: string | null; received_at: string | null; awaiting_confirmation: boolean; status: Status;
}
export interface GraphNode { id: string; floor: number; x: number; y: number; kind: 'corridor' | 'stairs' | 'elevator'; label: string }
export interface GraphEdge { id: string; from: string; to: string; distance_m: number | null }
export interface Graph { nodes: GraphNode[]; edges: GraphEdge[] }
export interface RoutePoint { id: string; floor: number; x: number; y: number; kind: string }
export interface Route {
  worker: number; color: string; bin_ids: string[]; distance_m: number; duration_seconds: number; path: RoutePoint[];
  sequence?: string[]; drops?: number; over_limit?: boolean;
}
export interface Plan {
  created_at: string; signature: string; include_orange: boolean; available_staff: number; mode?: RouteMode;
  routes: Route[]; target_ids: string[]; unreachable: string[]; unassigned: string[];
  total_distance_m: number; makespan_seconds: number; method: string; outdated: boolean;
  end?: 'DEPOT' | 'OFFICE'; total_seconds?: number; max_work_seconds?: number | null;
  comparison?: Record<RouteMode, { workers: number; total_distance_m: number; makespan_seconds: number; total_seconds?: number }>;
}
export interface CollectionLog {
  id: string; bin_id: string; floor: number; name: string; fill_before: number; worker: number | null;
  actor: string; source: string; completed_at: string;
}
export interface Reading { bin_id: string; fill: number | null; source: string; at: string }
export interface Workspace {
  user: User; building: Building; bins: Bin[]; graph: Graph; map_images: Record<string, string>;
  logs: CollectionLog[]; readings: Reading[]; last_plan: Plan | null; device_key_hint: string | null;
  revision: number; updated_at: string;
}
export const statusText: Record<Status, string> = {
  normal: '정상', warning: '주의', critical: '수거 필요', offline: '수신 대기', pending: '수거 확인 중',
};
export const statusColor: Record<Status, string> = {
  normal: '#3d8a5c', warning: '#e39a1f', critical: '#d64a3a', offline: '#9aa29d', pending: '#5a7db5',
};
export const sourceText: Record<string, string> = { actual: '실물 센서', simulated: '실물 위치 · 시뮬레이션', demo: '더미 데이터', unconnected: '실물 연동 대기' };
export function dateTime(value: string | null, short = false) {
  if (!value) return '아직 수신한 값이 없습니다';
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ...(short ? {} : { month: '2-digit', day: '2-digit' }), hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}
export function duration(seconds: number) {
  if (!seconds) return '0분';
  return seconds < 60 ? `${Math.round(seconds)}초` : `${Math.floor(seconds / 60)}분 ${Math.round(seconds % 60)}초`;
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, credentials: 'same-origin' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === 'string' ? data.detail : '입력값을 확인한 뒤 다시 시도해 주세요.';
    throw Object.assign(new Error(message), { status: response.status });
  }
  return response.json();
}
export function payload(data: unknown): RequestInit { return { method: 'POST', body: JSON.stringify(data) }; }
