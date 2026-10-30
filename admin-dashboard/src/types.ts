export type Page = 'dashboard' | 'map' | 'team' | 'history' | 'device' | 'settings';
export type Status = 'normal' | 'warning' | 'critical' | 'offline' | 'pending';
export type RouteMode = 'fastest' | 'lean';
export interface User { id: number; name: string; email: string }
export interface Building {
  name: string; floors: number; total_staff: number; available_staff: number;
  include_orange: boolean; route_mode?: RouteMode; meters_per_unit: number; speed_mps: number;
  service_seconds: number; warning_threshold: number; critical_threshold: number; stale_minutes: number;
  stairs_up_seconds?: number; stairs_down_seconds?: number; elevator_wait_seconds?: number; elevator_floor_seconds?: number;
  use_cart?: boolean; cart_capacity?: number; unload_seconds?: number; compartment_seconds?: number; max_work_minutes?: number;
}
export interface Bin {
  id: string; name: string; floor: number; x: number; y: number; access_node: string;
  fill: number | null; compartments: Fills; pending_compartments?: Compartment[]; device_type: 'real' | 'demo';
  reading_source: 'actual' | 'simulated' | 'demo' | 'unconnected';
  measured_at: string | null; received_at: string | null; awaiting_confirmation: boolean; status: Status;
}
export interface GraphNode {
  id: string; floor: number; x: number; y: number; kind: 'corridor' | 'stairs' | 'elevator' | 'office' | 'depot'; label: string;
  closed?: boolean; // a stair or lift stop out of service (운영 중단)
}
export interface GraphEdge { id: string; from: string; to: string; distance_m: number | null }
export interface Graph { nodes: GraphNode[]; edges: GraphEdge[] }
export interface RoutePoint { id: string; floor: number; x: number; y: number; kind: string }
export interface Route {
  worker: number; color: string; bin_ids: string[]; distance_m: number; duration_seconds: number; path: RoutePoint[];
  start?: string; sequence?: string[]; drops?: number; over_limit?: boolean;
}
export interface Plan {
  created_at: string; signature: string; include_orange: boolean; available_staff: number; mode?: RouteMode;
  routes: Route[]; target_ids: string[]; unreachable: string[]; unassigned: string[];
  total_distance_m: number; makespan_seconds: number; method: string; outdated: boolean;
  end?: 'DEPOT' | 'OFFICE'; issues?: string[]; empty?: Record<string, Partial<Fills>>; total_seconds?: number; max_work_seconds?: number | null;
  comparison?: Record<RouteMode, { workers: number; total_distance_m: number; makespan_seconds: number; total_seconds?: number }>;
}
export interface CollectionLog {
  id: string; bin_id: string; floor: number; name: string; fill_before: number; emptied?: Partial<Fills>; worker: number | null;
  actor: string; source: string; completed_at: string;
}
export interface Reading { bin_id: string; fill: number | null; fills?: Partial<Fills> | null; source: string; at: string }
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
// One location holds four compartments, as the device sorts them; each has its own sensor value and
// the location's fill is its fullest compartment.
export type Compartment = 'CAN' | 'PET' | 'GLASS' | 'OTHER';
export type Fills = Record<Compartment, number | null>;
export const compartments: Compartment[] = ['CAN', 'PET', 'GLASS', 'OTHER'];
export const compartmentName: Record<Compartment, string> = { CAN: '캔', PET: 'PET', GLASS: '유리', OTHER: '일반' };
export function fillStatus(fill: number | null, b: Building): Status {
  return fill === null ? 'offline' : fill >= b.critical_threshold ? 'critical' : fill >= b.warning_threshold ? 'warning' : 'normal';
}
export const fillText = (values: Partial<Fills>) => compartments.filter(c => values[c] != null).map(c => `${compartmentName[c]} ${values[c]}%`).join(' · ');
export function topCompartment(values: Fills): Compartment | null {
  const known = compartments.filter(c => values[c] !== null);
  return known.length ? known.reduce((a, c) => values[c]! > values[a]! ? c : a) : null;
}
// what a visit empties: every compartment at the warning level or above (all of them if none is), as the server does
export function toEmpty(values: Fills, b: Building): Partial<Fills> {
  const known = compartments.filter(c => values[c] !== null), over = known.filter(c => values[c]! >= b.warning_threshold);
  return Object.fromEntries((over.length ? over : known).map(c => [c, values[c]]));
}
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
