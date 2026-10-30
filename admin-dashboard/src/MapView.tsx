import { useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { Route, Workspace } from './types';
import { statusColor } from './types';

interface Props {
  workspace: Workspace; floor: number; routes?: Route[]; selectedBin?: string;
  selectedNodes?: string[]; showGraph?: boolean; editing?: boolean;
  onBinClick?: (id: string) => void; onNodeClick?: (id: string) => void;
  onPlace?: (x: number, y: number) => void;
  onMove?: (kind: 'bin' | 'office' | 'node', id: string, x: number, y: number) => void;
}
const px = (x: number) => x * 9 + 50;
const py = (y: number) => y * 4.6 + 45;

interface Point { x: number; y: number }
interface Leg { points: Point[]; back: boolean }

// Shift a polyline to the right of its direction of travel (SVG y points down), so the way out and the
// way back along the same corridor become two side-by-side lanes instead of one line.
function keepRight(points: Point[], offset: number): Point[] {
  const normals = points.slice(1).map((p, i) => {
    const dx = p.x - points[i].x, dy = p.y - points[i].y, length = Math.hypot(dx, dy) || 1;
    return { x: -dy / length, y: dx / length };
  });
  if (!normals.length) return points;
  return points.map((p, i) => {
    const a = normals[Math.max(0, i - 1)], b = normals[Math.min(normals.length - 1, i)];
    let nx = a.x + b.x, ny = a.y + b.y;
    const length = Math.hypot(nx, ny);
    if (length < 1e-6) { nx = b.x; ny = b.y; } else { nx /= length; ny /= length; }
    const scale = offset / Math.max(nx * b.x + ny * b.y, 0.5);
    return { x: p.x + nx * scale, y: p.y + ny * scale };
  });
}

// Arrowheads every ~90 map units along a polyline (at least one in the middle).
function arrowsAlong(points: Point[]) {
  const parts = points.slice(1).map((p, i) => ({ a: points[i], b: p, length: Math.hypot(p.x - points[i].x, p.y - points[i].y) }));
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  if (total < 28) return [];
  const marks = total < 120 ? [total / 2] : Array.from({ length: Math.floor((total - 30) / 90) + 1 }, (_, i) => 45 + i * 90);
  return marks.map(mark => {
    let walked = 0;
    const part = parts.find(p => (walked += p.length) >= mark) ?? parts[parts.length - 1];
    const t = part.length ? 1 - (walked - mark) / part.length : 0;
    return { x: part.a.x + (part.b.x - part.a.x) * t, y: part.a.y + (part.b.y - part.a.y) * t,
      angle: Math.atan2(part.b.y - part.a.y, part.b.x - part.a.x) * 180 / Math.PI };
  });
}

// The legs one route walks on one floor; the walk to the end point after the last stop is marked.
function routeOnFloor(route: Route, floor: number) {
  const path = route.path, at = (i: number) => ({ x: px(path[i].x), y: py(path[i].y) });
  const turn = path.map(p => p.id).lastIndexOf(route.bin_ids[route.bin_ids.length - 1]);
  const legs: Leg[] = [];
  let leg: Leg | null = null;
  for (let i = 0; i + 1 < path.length; i++) {
    if (path[i].floor !== floor || path[i + 1].floor !== floor) { leg = null; continue; }
    const back = i >= turn;
    if (!leg || leg.back !== back) { leg = { points: [at(i)], back }; legs.push(leg); }
    leg.points.push(at(i + 1));
  }
  return { legs };
}

export default function MapView({ workspace: s, floor, routes = [], selectedBin, selectedNodes = [], showGraph = false, editing, onBinClick, onNodeClick, onPlace, onMove }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ kind: 'bin' | 'office' | 'node'; id: string; x: number; y: number; moved: boolean } | null>(null);
  const moveRef = useRef(false);
  const nodes = s.graph.nodes.filter(n => n.floor === floor);
  const point = (event: { clientX: number; clientY: number }) => {
    const rect = svg.current!.getBoundingClientRect();
    return { x: Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width * 1000 - 50) / 9)),
      y: Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height * 560 - 45) / 4.6)) };
  };
  function startDrag(e: ReactPointerEvent, kind: 'bin' | 'office' | 'node', id: string, x: number, y: number) {
    if (!editing || !onMove) return;
    e.stopPropagation();
    svg.current!.setPointerCapture(e.pointerId);
    moveRef.current = false;
    setDrag({ kind, id, x, y, moved: false });
  }
  const location = (id: string, x: number, y: number) => drag?.id === id ? drag : { x, y };
  const floorImage = s.map_images[String(floor)];
  const views = routes.map(route => ({ route, ...routeOnFloor(route, floor) }));
  return <div className={`building-map ${editing ? 'editable' : ''}`}>
    <svg ref={svg} viewBox="0 0 1000 560" preserveAspectRatio="none" role="img" aria-label={`${floor}층 쓰레기통 및 관리자실 배치도`}
      onClick={e => { if (!moveRef.current) { const p = point(e); onPlace?.(p.x, p.y); } moveRef.current = false; }}
      onPointerMove={e => { if (drag) { const p = point(e); if (Math.abs(p.x - drag.x) + Math.abs(p.y - drag.y) > 0.25) moveRef.current = true; setDrag({ ...drag, ...p, moved: moveRef.current }); } }}
      onPointerUp={e => { if (drag) { if (drag.moved) { const p = point(e); onMove?.(drag.kind, drag.id, +p.x.toFixed(1), +p.y.toFixed(1)); } else if (drag.kind === 'bin') { onBinClick?.(drag.id); } else if (drag.kind === 'node') { onNodeClick?.(drag.id); } setDrag(null); svg.current?.releasePointerCapture(e.pointerId); } }}
      onPointerCancel={() => setDrag(null)}>
      <defs>
        <pattern id="map-grid" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.65" fill="#dce3df" /></pattern>
      </defs>
      <rect width="1000" height="560" fill="#f7f9f6" />
      <rect width="1000" height="560" fill="url(#map-grid)" />
      {floorImage ? <image href={`/api/floorplan/${floor}?v=${floorImage}`} x="50" y="45" width="900" height="460" preserveAspectRatio="none" opacity="0.72" /> : <g className="blueprint">
        <rect x="50" y="45" width="900" height="460" rx="5" fill="#fcfdfb" stroke="#ced8d0" strokeWidth="3" />
        <rect x="52" y="225" width="896" height="100" fill="#edf1eb" />
        {[50, 280, 510, 740].map((x, i) => <g key={x}>
          <path d={`M ${x} 225 V 45 M ${x} 325 V 505`} stroke="#ced8d0" strokeWidth="3" />
          <path d={`M ${x} 225 h ${i === 3 ? 210 : 230} M ${x} 325 h ${i === 3 ? 210 : 230}`} stroke="#ced8d0" strokeWidth="3" />
          <text x={x + 105} y="94" textAnchor="middle" fill="#6f7c73" fontSize="18" fontWeight="500">{[`${floor}01 강의실`, '세미나실', `${floor}02 강의실`, '공용 공간'][i]}</text>
          <text x={x + 110} y="490" textAnchor="middle" fill="#6f7c73" fontSize="18" fontWeight="500">{floor === 1 && i === 0 ? '시설 관리 구역' : ['휴게 공간', '라운지', '자료실', '공용 공간'][i]}</text>
        </g>)}
        {s.bins.filter(b => b.floor === floor).map(b => <rect key={`door-${b.id}`} x={px(b.x) - 20} y={b.y < 50 ? 221 : 321} width="40" height="8" fill="#fcfdfb" />)}
        {s.building.office_floor === floor && <rect x={px(s.building.office_x) - 20} y={s.building.office_y < 50 ? 221 : 321} width="40" height="8" fill="#fcfdfb" />}
        <rect x="860" y="238" width="70" height="75" rx="5" fill="#e1e8dd" stroke="#c5d1c0" />
        {[0, 1, 2, 3, 4].map(i => <line key={i} x1={873 + i * 9} y1="249" x2={873 + i * 9} y2="296" stroke="#b2c0ad" strokeWidth="2" />)}
        <text x="480" y="312" textAnchor="middle" fontSize="14" fill="#8d998f" letterSpacing="6">CORRIDOR</text>
        <g fill="#d6e0c8"><circle cx="78" cy="75" r="10" /><circle cx="84" cy="87" r="8" /><circle cx="920" cy="468" r="11" /></g>
      </g>}
      {s.graph.edges.map(edge => {
        const a = nodes.find(n => n.id === edge.from), b = nodes.find(n => n.id === edge.to);
        if (!a || !b) return null;
        const aa = location(a.id, a.x, a.y), bb = location(b.id, b.x, b.y);
        return <line key={edge.id} x1={px(aa.x)} y1={py(aa.y)} x2={px(bb.x)} y2={py(bb.y)} stroke={showGraph ? '#95ad9d' : '#d0d9cc'} strokeWidth={showGraph ? 4 : 2} strokeDasharray={showGraph ? '7 5' : '3 7'} />;
      })}
      {views.map(({ route, legs }, lane) => <g key={route.worker} className="map-route">{legs.map((leg, i) => {
        const points = keepRight(leg.points, 6 + lane * 7);
        const line = points.map(p => `${p.x},${p.y}`).join(' ');
        return <g key={i}>
          <polyline points={line} fill="none" stroke="#fff" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
          <polyline points={line} fill="none" stroke={route.color} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={leg.back ? '1 9' : undefined} />
          {arrowsAlong(points).map((a, j) => <path key={j} d="M 8 0 L -5 -7 L -2 0 L -5 7 Z" transform={`translate(${a.x} ${a.y}) rotate(${a.angle})`} fill={route.color} stroke="#fff" strokeWidth="1.5" strokeLinejoin="round" />)}
        </g>;
      })}</g>)}
      {nodes.map(n => {
        const p = location(n.id, n.x, n.y);
        return showGraph ? <g key={n.id} className="map-interactive" role="button" tabIndex={0} aria-label={`통로 ${n.id}`}
          onClick={e => { e.stopPropagation(); if (!moveRef.current) onNodeClick?.(n.id); }}
          onKeyDown={e => { if (e.key === 'Enter') onNodeClick?.(n.id); }}
          onPointerDown={e => startDrag(e, 'node', n.id, n.x, n.y)}>
          <circle cx={px(p.x)} cy={py(p.y)} r="10" fill={selectedNodes.includes(n.id) ? '#244b3d' : '#fff'} stroke="#648b76" strokeWidth="3" />
          <text x={px(p.x)} y={py(p.y) - 17} textAnchor="middle" fontSize="12" fontWeight="600" fill="#3f5a4b">{n.id}</text>
          <title>{n.label} · {n.kind === 'stairs' ? '계단' : n.kind === 'elevator' ? '엘리베이터' : '통로'}</title>
        </g> : n.kind !== 'corridor' ? <g key={n.id}><text x={px(p.x)} y={py(p.y) + 54} textAnchor="middle" fontSize="16" fontWeight="600" fill="#4f5f55">{n.kind === 'stairs' ? '계단 ↕' : '승강기 ↕'}</text></g> : null;
      })}
      {s.building.office_floor === floor && (() => {
        const p = location('OFFICE', s.building.office_x, s.building.office_y);
        return <g className={editing ? 'map-interactive' : ''} onClick={e => e.stopPropagation()} onPointerDown={e => startDrag(e, 'office', 'OFFICE', p.x, p.y)}>
          <circle cx={px(p.x)} cy={py(p.y)} r="24" fill="#244b3d" stroke="#fff" strokeWidth="4" />
          <path d={`M ${px(p.x) - 11} ${py(p.y) - 1} l 11 -10 11 10 M ${px(p.x) - 8} ${py(p.y) - 2} v 12 h 16 v -12 M ${px(p.x) - 2} ${py(p.y) + 10} v -8 h 4 v 8`} fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
          <rect x={px(p.x) - 42} y={py(p.y) + 28} width="84" height="27" rx="7" fill="#244b3d" />
          <text x={px(p.x)} y={py(p.y) + 47} fill="white" fontSize="16" fontWeight="600" textAnchor="middle">관리자실</text>
          <title>관리자실 · 수거 출발 및 복귀 지점</title>
        </g>;
      })()}
      {(() => {
        // The drop-off point (분리수거장) where every trip ends and the cart is emptied.
        const depot = s.graph.nodes.find(n => n.id === s.building.depot_node);
        if (!depot || depot.floor !== floor) return null;
        const x = px(depot.x), y = py(depot.y);
        return <g className="map-depot">
          <rect x={x - 21} y={y - 21} width="42" height="42" rx="10" fill="#33415c" stroke="#fff" strokeWidth="4" />
          <path d={`M ${x - 10} ${y + 1} h 6 l 2 4 h 4 l 2 -4 h 6 v 8 h -20 z M ${x} ${y - 12} v 9 M ${x - 4} ${y - 7} l 4 4 4 -4`} fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          <rect x={x - 46} y={y + 25} width="92" height="27" rx="7" fill="#33415c" />
          <text x={x} y={y + 44} fill="white" fontSize="16" fontWeight="600" textAnchor="middle">분리수거장</text>
          <title>분리수거장 · 수거한 쓰레기를 비우는 곳</title>
        </g>;
      })()}
      {s.bins.filter(b => b.floor === floor).map(bin => {
        const p = location(bin.id, bin.x, bin.y);
        const assigned = routes.find(r => r.bin_ids.includes(bin.id));
        return <g key={bin.id} className="map-interactive" role="button" tabIndex={0} aria-label={`${bin.id} ${bin.fill ?? '미수신'}%`}
          onClick={e => { e.stopPropagation(); if (!moveRef.current) onBinClick?.(bin.id); }}
          onKeyDown={e => { if (e.key === 'Enter') onBinClick?.(bin.id); }}
          onPointerDown={e => startDrag(e, 'bin', bin.id, bin.x, bin.y)}>
          {selectedBin === bin.id && <circle cx={px(p.x)} cy={py(p.y)} r="29" fill="none" stroke="#244b3d" strokeWidth="2" strokeDasharray="4 3" />}
          <circle cx={px(p.x)} cy={py(p.y)} r="21" fill={statusColor[bin.status]} stroke="white" strokeWidth="4" />
          <path d={`M ${px(p.x) - 7} ${py(p.y) - 7} h 14 l -1.5 16 h -11 z M ${px(p.x) - 10} ${py(p.y) - 10} h 20 M ${px(p.x) - 4} ${py(p.y) - 14} h 8`} fill="none" stroke="white" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          <rect x={px(p.x) - 38} y={py(p.y) + 25} width="76" height="27" rx="7" fill="white" stroke="#d3dbd0" />
          <text x={px(p.x)} y={py(p.y) + 44} textAnchor="middle" fill="#1f2e27" fontSize="16" fontWeight="700">{bin.id}</text>
          {assigned && <g><circle cx={px(p.x) + 21} cy={py(p.y) - 18} r="13" fill={assigned.color} stroke="white" strokeWidth="2.5" /><text x={px(p.x) + 21} y={py(p.y) - 13} textAnchor="middle" fill="white" fontSize="14" fontWeight="700">{assigned.bin_ids.indexOf(bin.id) + 1}</text></g>}
          <title>{bin.name} · {bin.fill === null ? '연결 대기' : `${bin.fill}%`}{assigned ? ` · 관리자 ${assigned.worker}` : ''}</title>
        </g>;
      })}
      <text x="28" y="30" fill="#4f5f55" fontSize="15" fontWeight="700">{floor}F FLOOR PLAN</text>
      <g transform="translate(845,538)"><line x1="0" y1="0" x2="90" y2="0" stroke="#6f7c73" /><line x1="0" y1="-4" x2="0" y2="4" stroke="#6f7c73" /><line x1="90" y1="-4" x2="90" y2="4" stroke="#6f7c73" /><text x="45" y="-8" textAnchor="middle" fontSize="14" fill="#5f6c64">{(10 * s.building.meters_per_unit).toFixed(0)}m</text></g>
    </svg>
  </div>;
}
