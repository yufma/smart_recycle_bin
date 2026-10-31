import type { Bin, Building, Graph, GraphNode } from './types';

export type CoreKind = 'stairs' | 'elevator';
// A stair or lift: one code (ST1, EL1, ...) with a stop on every floor it was placed on. Stops of one
// stair or lift are linked floor to floor automatically; a closed stop (운영 중단) is skipped.
export interface Shaft { code: string; kind: CoreKind; name: string; nodes: Map<number, GraphNode> }
export interface PendingShaft { code: string; kind: CoreKind; name: string }

export const kindName: Record<GraphNode['kind'], string> = { corridor: '복도', office: '관리자실', depot: '분리수거장', stairs: '계단', elevator: '엘리베이터' };
// A name with 이/가 (or another particle pair) by its last sound; digits are read in Korean.
export function josa(word: string, withFinal: string, without: string) {
  const last = word.trim().slice(-1), code = last.charCodeAt(0) - 0xac00;
  const final = code >= 0 && code < 11172 ? code % 28 > 0 : /[013678]/.test(last) ? true : /[2459]/.test(last) ? false : null;
  return word + (final === null ? `${withFinal}(${without})` : final ? withFinal : without);
}
export const isCore = (node: GraphNode) => node.kind === 'stairs' || node.kind === 'elevator';
const PREFIX = { office: 'OF', depot: 'DP', stairs: 'ST', elevator: 'EL' } as const;

// The part of a point id after its floor prefix ("F2-EL1" -> "EL1"); the map shows only this.
export const shortCode = (node: GraphNode) => node.id.startsWith(`F${node.floor}-`) ? node.id.slice(`F${node.floor}-`.length) : node.id;

// Ids for new points: corridors are numbered per floor (F1-1, F1-2, ...); offices and drop-off points
// are numbered across the building (F1-OF1, F3-OF2, F1-DP1).
export function newPoint(graph: Graph, floor: number, kind: 'corridor' | 'office' | 'depot'): { id: string; label: string } {
  const taken = new Set(graph.nodes.map(n => n.id));
  if (kind === 'corridor') {
    let k = 1;
    while (taken.has(`F${floor}-${k}`)) k++;
    return { id: `F${floor}-${k}`, label: `통로 ${k}` };
  }
  const used = new Set(graph.nodes.filter(n => n.kind === kind).map(shortCode));
  let k = 1;
  while (used.has(`${PREFIX[kind]}${k}`) || taken.has(`F${floor}-${PREFIX[kind]}${k}`)) k++;
  return { id: `F${floor}-${PREFIX[kind]}${k}`, label: k === 1 ? kindName[kind] : `${kindName[kind]} ${k}` };
}

// The next free code for a new stair or lift (ST1, ST2, ... / EL1, ...).
export function newShaft(graph: Graph, pending: PendingShaft[], kind: CoreKind): PendingShaft {
  const used = new Set([...graph.nodes.filter(isCore).map(shortCode), ...pending.map(p => p.code)]);
  let k = 1;
  while (used.has(`${PREFIX[kind]}${k}`)) k++;
  return { code: `${PREFIX[kind]}${k}`, kind, name: `${kindName[kind]} ${k}` };
}

const linked = (e: Graph['edges'][number], a: string, b: string) => (e.from === a && e.to === b) || (e.from === b && e.to === a);

// Stairs and lifts by code; older buildings whose stops carry different codes but are joined floor
// to floor still count as one.
export function shafts(graph: Graph, pending: PendingShaft[] = []): Shaft[] {
  const cores = graph.nodes.filter(isCore);
  const parent = new Map(cores.map(n => [n.id, n.id]));
  const root = (id: string): string => { const p = parent.get(id)!; return p === id ? id : root(p); };
  const join = (a: string, b: string) => parent.set(root(a), root(b));
  const byCode = new Map<string, string>();
  cores.forEach(n => { const key = `${n.kind}:${shortCode(n)}`; if (byCode.has(key)) join(n.id, byCode.get(key)!); else byCode.set(key, n.id); });
  const floorOf = new Map(cores.map(n => [n.id, n.floor]));
  graph.edges.forEach(e => { if (parent.has(e.from) && parent.has(e.to) && floorOf.get(e.from) !== floorOf.get(e.to)) join(e.from, e.to); });
  const groups = new Map<string, GraphNode[]>();
  cores.forEach(n => groups.set(root(n.id), [...(groups.get(root(n.id)) ?? []), n]));
  const placed: Shaft[] = [...groups.values()].map(members => {
    members.sort((a, b) => a.floor - b.floor);
    const nodes = new Map<number, GraphNode>();
    members.forEach(n => { if (!nodes.has(n.floor)) nodes.set(n.floor, n); });
    return { code: shortCode(members[0]), kind: members[0].kind as CoreKind, name: members[0].label, nodes };
  });
  const codes = new Set(placed.map(sh => sh.code));
  const waiting = pending.filter(p => !codes.has(p.code)).map(p => ({ ...p, nodes: new Map<number, GraphNode>() }));
  const order = (sh: Shaft) => [sh.kind === 'stairs' ? 0 : 1, Number(sh.code.replace(/\D/g, '')) || 0] as const;
  return [...placed, ...waiting].sort((a, b) => order(a)[0] - order(b)[0] || order(a)[1] - order(b)[1] || a.code.localeCompare(b.code));
}

// Link the open stops of one stair or lift floor by floor, from the lowest; closed stops get no
// floor-to-floor link, so the floors above and below one are linked past it. A link the saved
// building already has is reused as it was, so undoing a change leaves nothing to save.
function relink(nodes: GraphNode[], edges: Graph['edges'], members: Set<string>, saved: Graph['edges'] = []): Graph {
  const floorOf = new Map(nodes.map(n => [n.id, n.floor]));
  const old = edges.filter(e => (members.has(e.from) || members.has(e.to)) && floorOf.get(e.from) !== floorOf.get(e.to));
  const kept = edges.filter(e => !old.includes(e));
  const open = nodes.filter(n => members.has(n.id) && !n.closed).sort((a, b) => a.floor - b.floor);
  open.slice(1).forEach((upper, i) => {
    const a = open[i].id, b = upper.id;
    kept.push(old.find(e => linked(e, a, b)) ?? saved.find(e => linked(e, a, b)) ?? { id: `V-${a}-${b}`, from: a, to: b, distance_m: null });
  });
  return { nodes, edges: kept };
}
const memberIds = (shaft: Shaft) => new Set([...shaft.nodes.values()].map(n => n.id));

// Put this stair or lift on a floor at (x, y), or move its stop there if the floor already has one.
// Nothing is joined to the corridor: that link is drawn by hand with '통로 연결'.
export function placeStop(graph: Graph, shaft: Shaft, floor: number, x: number, y: number, saved?: Graph): Graph | string {
  const here = shaft.nodes.get(floor);
  if (here) return { ...graph, nodes: graph.nodes.map(n => n.id === here.id ? { ...n, x, y } : n) };
  const id = `F${floor}-${shaft.code}`;
  if (graph.nodes.some(n => n.id === id)) return `${floor}층에 이미 ${shaft.code} 번호를 쓰는 지점이 있습니다.`;
  const node: GraphNode = { id, floor, x, y, kind: shaft.kind, label: shaft.name };
  return relink([...graph.nodes, node], graph.edges, new Set([...memberIds(shaft), id]), saved?.edges);
}

// 운영 중단: the stop stays on the map with its corridor links, but nobody gets on or off there.
export function setStopOpen(graph: Graph, shaft: Shaft, floor: number, open: boolean, saved?: Graph): Graph {
  const stop = shaft.nodes.get(floor);
  if (!stop) return graph;
  const nodes = graph.nodes.map(n => n.id === stop.id ? { ...n, closed: !open } : n);
  return relink(nodes, graph.edges, memberIds(shaft), saved?.edges);
}

export function removeStop(graph: Graph, shaft: Shaft, id: string, saved?: Graph): Graph {
  const members = memberIds(shaft);
  members.delete(id);
  return relink(graph.nodes.filter(n => n.id !== id), graph.edges.filter(e => e.from !== id && e.to !== id), members, saved?.edges);
}

// Same points and links in any order: an edit that was undone by hand leaves nothing to save.
export function sameGraph(a: Graph, b: Graph) {
  const key = (g: Graph) => JSON.stringify([
    [...g.nodes].sort((p, q) => p.id.localeCompare(q.id)).map(n => [n.id, n.floor, n.x, n.y, n.kind, n.label, !!n.closed]),
    [...g.edges].sort((p, q) => p.id.localeCompare(q.id)).map(e => [e.id, e.from, e.to, e.distance_m ?? null])]);
  return key(a) === key(b);
}

export interface LinkProblem { text: string; bins: string[] }

// Can every bin and drop-off point be reached from an office? Works on the unsaved draft too. With a
// cart the stairs cannot be used between floors, and closed stops never, as in route planning.
export function linkCheck(graph: Graph, building: Building, bins: Bin[]) {
  const byId = new Map(graph.nodes.map(n => [n.id, n]));
  const next = new Map(graph.nodes.map(n => [n.id, [] as string[]]));
  graph.edges.forEach(e => {
    const a = byId.get(e.from), b = byId.get(e.to);
    if (!a || !b) return;
    next.get(a.id)!.push(b.id);
    next.get(b.id)!.push(a.id);
  });
  const walk = new Map(graph.nodes.map(n => [n.id, [] as string[]]));
  graph.edges.forEach(e => {
    const a = byId.get(e.from), b = byId.get(e.to);
    if (!a || !b) return;
    if (a.floor !== b.floor && (a.closed || b.closed || (building.use_cart && a.kind === 'stairs'))) return;
    walk.get(a.id)!.push(b.id);
    walk.get(b.id)!.push(a.id);
  });
  const offices = graph.nodes.filter(n => n.kind === 'office');
  const depots = graph.nodes.filter(n => n.kind === 'depot');
  const reached = new Set(offices.map(n => n.id));
  const queue = [...reached];
  while (queue.length) for (const id of walk.get(queue.shift()!) ?? []) if (!reached.has(id)) { reached.add(id); queue.push(id); }
  const floorsReached = new Set([...reached].filter(id => next.get(id)!.length).map(id => byId.get(id)!.floor));
  const problems: LinkProblem[] = [];
  if (!offices.length) problems.push({ text: "관리자실이 없습니다. '지점 설정'에서 관리자실을 놓아 주세요.", bins: [] });
  offices.filter(o => !next.get(o.id)!.length).forEach(o => problems.push({ text: `${o.floor}층 ${josa(o.label, '이', '가')} 통로와 이어져 있지 않습니다.`, bins: [] }));
  const cart = building.use_cart ? ' 카트를 쓰면 계단으로는 층을 옮길 수 없습니다.' : '';
  const lost = offices.length ? bins.filter(b => !reached.has(b.access_node)) : [];
  const byFloor = new Map<number, Bin[]>();
  lost.forEach(b => byFloor.set(b.floor, [...(byFloor.get(b.floor) ?? []), b]));
  [...byFloor.entries()].sort((a, b) => a[0] - b[0]).forEach(([floor, group]) => {
    if (!floorsReached.has(floor)) {
      problems.push({ text: `${floor}층이 관리자실과 이어져 있지 않습니다.${cart}`, bins: group.map(b => b.id) });
      return;
    }
    group.forEach(b => {
      const node = byId.get(b.access_node);
      problems.push({ text: node ? `${b.floor}층 ${b.id}의 연결 통로(${node.label})가 이 층 복도와 이어져 있지 않습니다.` : `${b.id}의 연결 통로가 없습니다.`, bins: [b.id] });
    });
  });
  if (offices.length) depots.filter(d => !reached.has(d.id)).forEach(d => problems.push({ text: `${d.floor}층 ${josa(d.label, '이', '가')} 관리자실과 이어져 있지 않습니다.${cart}`, bins: [] }));
  const loose = graph.nodes.filter(n => !next.get(n.id)!.length && n.kind !== 'office');
  return { problems, loose, binCount: bins.length, depots: depots.length };
}
