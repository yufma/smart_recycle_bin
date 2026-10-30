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
  return <div className={`building-map ${editing ? 'editable' : ''}`}>
    <svg ref={svg} viewBox="0 0 1000 560" preserveAspectRatio="none" role="img" aria-label={`${floor}층 쓰레기통 및 관리자실 배치도`}
      onClick={e => { if (!moveRef.current) { const p = point(e); onPlace?.(p.x, p.y); } moveRef.current = false; }}
      onPointerMove={e => { if (drag) { const p = point(e); if (Math.abs(p.x - drag.x) + Math.abs(p.y - drag.y) > 0.25) moveRef.current = true; setDrag({ ...drag, ...p, moved: moveRef.current }); } }}
      onPointerUp={e => { if (drag) { if (drag.moved) { const p = point(e); onMove?.(drag.kind, drag.id, +p.x.toFixed(1), +p.y.toFixed(1)); } else if (drag.kind === 'bin') { onBinClick?.(drag.id); } else if (drag.kind === 'node') { onNodeClick?.(drag.id); } setDrag(null); svg.current?.releasePointerCapture(e.pointerId); } }}
      onPointerCancel={() => setDrag(null)}>
      <defs>
        <pattern id="map-grid" width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.65" fill="#dce3df" /></pattern>
        {routes.map(r => <marker key={r.worker} id={`arrow-${r.worker}`} viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M 0 1 L 7 5 L 0 9" fill="none" stroke={r.color} strokeWidth="2" /></marker>)}
      </defs>
      <rect width="1000" height="560" fill="#f7f9f6" />
      <rect width="1000" height="560" fill="url(#map-grid)" />
      {floorImage ? <image href={`/api/floorplan/${floor}?v=${floorImage}`} x="50" y="45" width="900" height="460" preserveAspectRatio="none" opacity="0.72" /> : <g className="blueprint">
        <rect x="50" y="45" width="900" height="460" rx="5" fill="#fcfdfb" stroke="#ced8d0" strokeWidth="3" />
        <rect x="52" y="225" width="896" height="100" fill="#edf1eb" />
        {[50, 280, 510, 740].map((x, i) => <g key={x}>
          <path d={`M ${x} 225 V 45 M ${x} 325 V 505`} stroke="#ced8d0" strokeWidth="3" />
          <path d={`M ${x} 225 h ${i === 3 ? 210 : 230} M ${x} 325 h ${i === 3 ? 210 : 230}`} stroke="#ced8d0" strokeWidth="3" />
          <text x={x + 105} y="92" textAnchor="middle" fill="#a3ada6" fontSize="14">{[`${floor}01 강의실`, '세미나실', `${floor}02 강의실`, '공용 공간'][i]}</text>
          <text x={x + 110} y="470" textAnchor="middle" fill="#a3ada6" fontSize="14">{floor === 1 && i === 0 ? '시설 관리 구역' : ['휴게 공간', '라운지', '자료실', '공용 공간'][i]}</text>
        </g>)}
        {s.bins.filter(b => b.floor === floor).map(b => <rect key={`door-${b.id}`} x={px(b.x) - 20} y={b.y < 50 ? 221 : 321} width="40" height="8" fill="#fcfdfb" />)}
        {s.building.office_floor === floor && <rect x={px(s.building.office_x) - 20} y={s.building.office_y < 50 ? 221 : 321} width="40" height="8" fill="#fcfdfb" />}
        <rect x="860" y="238" width="70" height="75" rx="5" fill="#e1e8dd" stroke="#c5d1c0" />
        {[0, 1, 2, 3, 4].map(i => <line key={i} x1={873 + i * 9} y1="249" x2={873 + i * 9} y2="296" stroke="#b2c0ad" strokeWidth="2" />)}
        <text x="480" y="310" textAnchor="middle" fontSize="12" fill="#acb7ae" letterSpacing="6">CORRIDOR</text>
        <g fill="#d6e0c8"><circle cx="78" cy="75" r="10" /><circle cx="84" cy="87" r="8" /><circle cx="920" cy="468" r="11" /></g>
      </g>}
      {s.graph.edges.map(edge => {
        const a = nodes.find(n => n.id === edge.from), b = nodes.find(n => n.id === edge.to);
        if (!a || !b) return null;
        const aa = location(a.id, a.x, a.y), bb = location(b.id, b.x, b.y);
        return <line key={edge.id} x1={px(aa.x)} y1={py(aa.y)} x2={px(bb.x)} y2={py(bb.y)} stroke={showGraph ? '#95ad9d' : '#d0d9cc'} strokeWidth={showGraph ? 4 : 2} strokeDasharray={showGraph ? '7 5' : '3 7'} />;
      })}
      {routes.flatMap(route => {
        const segments: typeof route.path[] = []; let current: typeof route.path = [];
        route.path.forEach(p => { if (p.floor === floor) current.push(p); else if (current.length) { segments.push(current); current = []; } });
        if (current.length) segments.push(current);
        return segments.filter(x => x.length > 1).map((segment, i) => <polyline key={`${route.worker}-${i}`} points={segment.map(p => `${px(p.x)},${py(p.y) + (route.worker - 1) * 5 - 2}`).join(' ')} fill="none" stroke={route.color} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" opacity="0.8" markerMid={`url(#arrow-${route.worker})`} />);
      })}
      {nodes.map(n => {
        const p = location(n.id, n.x, n.y);
        return showGraph ? <g key={n.id} className="map-interactive" role="button" tabIndex={0} aria-label={`통로 ${n.id}`}
          onClick={e => { e.stopPropagation(); if (!moveRef.current) onNodeClick?.(n.id); }}
          onKeyDown={e => { if (e.key === 'Enter') onNodeClick?.(n.id); }}
          onPointerDown={e => startDrag(e, 'node', n.id, n.x, n.y)}>
          <circle cx={px(p.x)} cy={py(p.y)} r="10" fill={selectedNodes.includes(n.id) ? '#244b3d' : '#fff'} stroke="#648b76" strokeWidth="3" />
          <text x={px(p.x)} y={py(p.y) - 17} textAnchor="middle" fontSize="11" fill="#537361">{n.id}</text>
          <title>{n.label} · {n.kind === 'stairs' ? '계단' : n.kind === 'elevator' ? '엘리베이터' : '통로'}</title>
        </g> : n.kind !== 'corridor' ? <g key={n.id}><text x={px(p.x)} y={py(p.y) + 52} textAnchor="middle" fontSize="12" fill="#71816f">{n.kind === 'stairs' ? '계단 ↕' : '승강기 ↕'}</text></g> : null;
      })}
      {s.building.office_floor === floor && (() => {
        const p = location('OFFICE', s.building.office_x, s.building.office_y);
        return <g className={editing ? 'map-interactive' : ''} onClick={e => e.stopPropagation()} onPointerDown={e => startDrag(e, 'office', 'OFFICE', p.x, p.y)}>
          <circle cx={px(p.x)} cy={py(p.y)} r="24" fill="#244b3d" stroke="#fff" strokeWidth="4" />
          <path d={`M ${px(p.x) - 11} ${py(p.y) - 1} l 11 -10 11 10 M ${px(p.x) - 8} ${py(p.y) - 2} v 12 h 16 v -12 M ${px(p.x) - 2} ${py(p.y) + 10} v -8 h 4 v 8`} fill="none" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
          <rect x={px(p.x) - 35} y={py(p.y) + 28} width="70" height="22" rx="6" fill="#244b3d" />
          <text x={px(p.x)} y={py(p.y) + 43} fill="white" fontSize="12" textAnchor="middle">관리자실</text>
          <title>관리자실 · 수거 출발 및 복귀 지점</title>
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
          <rect x={px(p.x) - 33} y={py(p.y) + 25} width="66" height="22" rx="6" fill="white" stroke="#e1e7df" />
          <text x={px(p.x)} y={py(p.y) + 40} textAnchor="middle" fill="#42554b" fontSize="12" fontWeight="600">{bin.id}</text>
          {assigned && <g><circle cx={px(p.x) + 20} cy={py(p.y) - 17} r="11" fill={assigned.color} stroke="white" strokeWidth="2" /><text x={px(p.x) + 20} y={py(p.y) - 13} textAnchor="middle" fill="white" fontSize="11" fontWeight="700">{assigned.bin_ids.indexOf(bin.id) + 1}</text></g>}
          <title>{bin.name} · {bin.fill === null ? '연결 대기' : `${bin.fill}%`}{assigned ? ` · 관리자 ${assigned.worker}` : ''}</title>
        </g>;
      })}
      <text x="28" y="28" fill="#718177" fontSize="12" fontWeight="700">{floor}F FLOOR PLAN</text>
      <g transform="translate(845,535)"><line x1="0" y1="0" x2="90" y2="0" stroke="#8f9f91" /><line x1="0" y1="-4" x2="0" y2="4" stroke="#8f9f91" /><line x1="90" y1="-4" x2="90" y2="4" stroke="#8f9f91" /><text x="45" y="-7" textAnchor="middle" fontSize="11" fill="#8f9f91">{(10 * s.building.meters_per_unit).toFixed(0)}m</text></g>
    </svg>
  </div>;
}
