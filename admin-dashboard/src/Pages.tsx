import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { AlertCircle, ArrowUpRight, Building2, Check, Clock3, Copy, Download, FileImage, Footprints, Home, KeyRound, Link2, Loader2, MapPin, MousePointer2, Plus, Radio, Recycle, RefreshCw, Save, Search, Settings2, ShieldCheck, Sparkles, Trash2, Upload, Users, X } from 'lucide-react';
import type { PageProps } from './App';
import type { Bin, Compartment, Graph, GraphNode } from './types';
import { api, compartmentName, compartments, dateTime, duration, fillText, payload, sourceText } from './types';
import { Badge, BinArt, CompartmentRow, Dialog, Empty, FloorTabs, SectionTitle, SensorNotice } from './UI';
import { RoutePanel } from './Dashboard';
import MapView from './MapView';
import { isCore, kindName, linkCheck, newPoint, newShaft, placeStop, removeStop, sameGraph, setStopOpen, shafts, shortCode } from './graphTools';
import type { CoreKind, PendingShaft, Shaft } from './graphTools';

function PageHeading({ eyebrow, title, children, action }: { eyebrow: string; title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <div className="page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title}<span className="heading-dot">.</span></h1><p>{children}</p></div>{action}</div>;
}
function formNumbers(form: HTMLFormElement) { return Object.fromEntries(Array.from(new FormData(form).entries()).map(([k, v]) => [k, ['name', 'access_node'].includes(k) ? String(v) : Number(v)])); }

type PlaceKind = 'corridor' | 'office' | 'depot';
const placeKinds: PlaceKind[] = ['corridor', 'office', 'depot'];
const placeIcon = { corridor: MapPin, office: Home, depot: Recycle };

export function BuildingEditor({ s, mutate, busy, notify }: PageProps) {
  const [floor, setFloor] = useState(1);
  const [mode, setMode] = useState<'move' | 'add-bin' | 'node' | 'connect'>('move');
  const [selected, setSelected] = useState('');
  const [draft, setDraft] = useState<Graph | null>(null);
  const [placing, setPlacing] = useState('corridor'); // a point kind, or the code of a stair or lift
  const [pending, setPending] = useState<PendingShaft[]>([]); // stairs and lifts added but not yet placed
  const [connectFrom, setConnectFrom] = useState('');
  const [newBin, setNewBin] = useState<{ x: number; y: number } | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [linkFor, setLinkFor] = useState<string | null>(null); // a bin whose access point is being picked on the map
  const [accessDraft, setAccessDraft] = useState('');
  const imageInput = useRef<HTMLInputElement>(null);
  const graph = draft || s.graph;
  const mapState = { ...s, graph };
  useEffect(() => { if (draft && sameGraph(draft, s.graph)) setDraft(null); }, [draft, s.graph]);
  const walkable = (n: GraphNode) => n.kind !== 'office' && n.kind !== 'depot';
  const floorNodes = graph.nodes.filter(n => n.floor === floor && walkable(n));
  const bin = s.bins.find(b => b.id === selected);
  useEffect(() => setAccessDraft(bin?.access_node ?? ''), [bin?.id, bin?.access_node]);
  useEffect(() => setLinkFor(null), [selected]);
  const node = selectedNode ? graph.nodes.find(n => n.id === selectedNode) : undefined;
  const shaftList = shafts(graph, pending);
  const shaftOf = (id: string) => shaftList.find(sh => [...sh.nodes.values()].some(n => n.id === id));
  const placingShaft = shaftList.find(sh => sh.code === placing);
  const placingKind = placeKinds.find(k => k === placing);
  const placingName = placingShaft ? `${kindName[placingShaft.kind]} ${placingShaft.code} · ${placingShaft.name}` : placingKind ? kindName[placingKind] : '';
  function nearest(x: number, y: number, targetFloor = floor) {
    return graph.nodes.filter(n => n.floor === targetFloor && walkable(n)).sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y))[0]?.id || '';
  }
  async function place(x: number, y: number) {
    if (linkFor) { setLinkFor(null); return; } // a click beside the points cancels picking
    const at = { x: +x.toFixed(1), y: +y.toFixed(1) };
    if (mode === 'move') { setSelected(''); setSelectedNode(null); }
    else if (mode === 'add-bin') { if (draft) { notify('지점·통로 변경 사항을 먼저 저장해 주세요.', 'error'); return; } if (!floorNodes.length) { notify('이 층에 복도 지점을 먼저 추가해 주세요.', 'error'); return; } setNewBin(at); }
    else if (mode === 'node') {
      // nothing is joined automatically: links are drawn with '통로 연결', except between the floors of one stair or lift
      if (placingShaft) { const next = placeStop(graph, placingShaft, floor, at.x, at.y, s.graph); if (typeof next === 'string') notify(next, 'error'); else setDraft(next); return; }
      if (!placingKind) { notify('오른쪽에서 놓을 지점을 골라 주세요.', 'error'); return; }
      const point = newPoint(graph, floor, placingKind);
      setDraft({ ...graph, nodes: [...graph.nodes, { id: point.id, floor, ...at, kind: placingKind, label: point.label }] });
    }
  }
  async function move(kind: 'bin' | 'node', id: string, x: number, y: number) {
    if (mode !== 'move') return;
    if (kind === 'node') { setDraft({ ...graph, nodes: graph.nodes.map(n => n.id === id ? { ...n, x, y } : n) }); return; }
    if (draft) { notify('지점·통로 변경 사항을 먼저 저장해 주세요.', 'error'); return; }
    if (!nearest(x, y)) { notify('같은 층의 연결 통로가 필요합니다.', 'error'); return; }
    await mutate(`/bins/${id}`, { x, y, access_node: nearest(x, y) }, 'PATCH');
  }
  function connect(to: string, from = connectFrom, distance: number | null = null) {
    if (!from) { setConnectFrom(to); return; }
    if (from === to) { setConnectFrom(''); return; }
    const a = graph.nodes.find(n => n.id === from)!, b = graph.nodes.find(n => n.id === to)!;
    if (a.floor !== b.floor && (!isCore(a) || a.kind !== b.kind)) { notify('층 사이는 같은 종류의 계단 또는 엘리베이터를 연결해 주세요.', 'error'); return; }
    if (graph.edges.some(e => (e.from === from && e.to === to) || (e.from === to && e.to === from))) { notify('이미 연결된 지점입니다.', 'error'); setConnectFrom(''); return; }
    const edgeId = graph.edges.some(e => e.id === `E-${from}-${to}`) ? `E-${from}-${to}-${Date.now().toString(36)}` : `E-${from}-${to}`;
    setDraft({ ...graph, edges: [...graph.edges, { id: edgeId, from, to, distance_m: distance }] });
    setConnectFrom('');
  }
  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
    if (file.size > 4_000_000) { notify('도면은 4MB 이하로 선택해 주세요.', 'error'); return; }
    const reader = new FileReader(); reader.onload = () => mutate(`/floorplan/${floor}`, { data_url: reader.result }, 'PUT', `${floor}층 도면을 저장했습니다.`); reader.readAsDataURL(file);
  }
  async function addBin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!newBin) return;
    const form = new FormData(e.currentTarget);
    const result = await mutate('/bins', { name: form.get('name'), floor, ...newBin, access_node: form.get('access_node'), fills: Object.fromEntries(compartments.map(c => [c, Number(form.get(c))])), device_type: 'demo' }, 'POST', '쓰레기통을 추가했습니다.');
    if (result) { setNewBin(null); setMode('move'); setSelected(result.bins[result.bins.length - 1].id); }
  }
  const check = linkCheck(graph, s.building, s.bins);
  const floorNumbers = Array.from({ length: s.building.floors }, (_, i) => i + 1);
  const pinned = new Set(s.bins.map(b => b.access_node));
  function removeNode(id: string) {
    const target = graph.nodes.find(n => n.id === id);
    if (!target) return;
    if (pinned.has(id)) { notify('쓰레기통이 연결된 지점입니다. 쓰레기통의 연결 통로를 먼저 바꿔 주세요.', 'error'); return; }
    const shaft = isCore(target) ? shaftOf(id) : undefined;
    // a stop of a stair or lift is taken out so the floors above and below stay linked
    setDraft(shaft ? removeStop(graph, shaft, id, s.graph) : { nodes: graph.nodes.filter(n => n.id !== id), edges: graph.edges.filter(e => e.from !== id && e.to !== id) });
    if (selectedNode === id) setSelectedNode(null);
  }
  function updateNode(target: GraphNode, label: string, kind: GraphNode['kind'], x: number, y: number) {
    // a stair or lift keeps one name on every floor it serves
    const shaft = isCore(target) ? shaftOf(target.id) : undefined;
    const same = new Set(shaft ? [...shaft.nodes.values()].map(n => n.id) : [target.id]);
    setDraft({ ...graph, nodes: graph.nodes.map(n => n.id === target.id ? { ...n, label, kind, x, y } : same.has(n.id) ? { ...n, label } : n) });
  }
  function choose(value: string) { setPlacing(value); setMode('node'); setSelected(''); setSelectedNode(null); setConnectFrom(''); }
  function addShaft(kind: CoreKind) { const shaft = newShaft(graph, pending, kind); setPending([...pending, shaft]); choose(shaft.code); }
  // a stair or lift as a whole: one name on every floor, and deleting it takes every floor's stop and link
  function renameShaft(shaft: Shaft, name: string) {
    if (!name || name === shaft.name) return;
    const ids = new Set([...shaft.nodes.values()].map(n => n.id));
    setPending(pending.map(p => p.code === shaft.code ? { ...p, name } : p));
    if (ids.size) setDraft({ ...graph, nodes: graph.nodes.map(n => ids.has(n.id) ? { ...n, label: name } : n) });
  }
  function removeShaft(shaft: Shaft) {
    const ids = new Set([...shaft.nodes.values()].map(n => n.id));
    const used = [...ids].filter(id => pinned.has(id));
    if (used.length) { notify(`${used.join(', ')}에 쓰레기통이 연결되어 있습니다. 쓰레기통의 연결 통로를 먼저 바꿔 주세요.`, 'error'); return; }
    setPending(pending.filter(p => p.code !== shaft.code));
    if (ids.size) setDraft({ nodes: graph.nodes.filter(n => !ids.has(n.id)), edges: graph.edges.filter(e => !ids.has(e.from) && !ids.has(e.to)) });
    setPlacing('corridor');
  }
  function pick(id: string) { setSelected(id); setSelectedNode(null); }
  function startLink(target: Bin) {
    if (linkFor === target.id) { setLinkFor(null); return; }
    if (draft) { notify('지점·통로 변경 사항을 먼저 저장해 주세요.', 'error'); return; }
    setMode('move'); setFloor(target.floor); setLinkFor(target.id);
  }
  async function linkTo(id: string) {
    const target = s.bins.find(b => b.id === linkFor), point = graph.nodes.find(n => n.id === id);
    if (!target || !point) return;
    if (!walkable(point)) { notify('복도·계단·엘리베이터 지점을 눌러 주세요.', 'error'); return; }
    if (point.floor !== target.floor) { notify(`${target.floor}층에 있는 지점을 눌러 주세요.`, 'error'); return; }
    const r = await mutate(`/bins/${target.id}`, { access_node: id }, 'PATCH', `${target.id} 연결 통로를 바꿨습니다: ${point.label}`);
    if (r) setLinkFor(null);
  }
  const tools = [{ id: 'move', icon: MousePointer2, label: '선택 · 이동' }, { id: 'add-bin', icon: Plus, label: '쓰레기통' }, { id: 'node', icon: MapPin, label: '지점 설정' }, { id: 'connect', icon: Link2, label: '통로 연결' }] as const;
  return <><PageHeading eyebrow="BUILDING & FLOOR PLAN" title="공간을 등록하고 연결하세요">쓰레기통과 관리자실을 배치하고, 실제로 걸을 수 있는 통로를 연결합니다.</PageHeading>
    <form className="building-basic panel" key={`${s.building.name}-${s.building.floors}`} onSubmit={e => { e.preventDefault(); mutate('/config', formNumbers(e.currentTarget), 'PATCH', '건물 정보를 저장했습니다.'); }}><label>건물 이름<input name="name" defaultValue={s.building.name} required maxLength={80} /></label><label className="small-field">층수<input name="floors" type="number" min="1" max="10" defaultValue={s.building.floors} required /></label><button className="button secondary" disabled={busy}><Save size={15} />건물 저장</button><span><Building2 size={16} /> 쓰레기통 {s.bins.length}개 등록됨</span></form>
    <div className="editor-grid"><section className="panel editor-main"><div className="map-toolbar"><FloorTabs value={floor} floors={s.building.floors} onChange={setFloor} /><div className="inline-actions"><button className="button subtle small" disabled={busy} onClick={() => imageInput.current?.click()}><FileImage size={14} />도면 업로드</button>{s.map_images[String(floor)] && <button className="icon-button" aria-label="기본 도면으로 변경" onClick={() => mutate(`/floorplan/${floor}`, { data_url: null }, 'PUT', '예시 도면으로 변경했습니다.')}><X size={15} /></button>}<input type="file" accept="image/png,image/jpeg,image/webp" hidden ref={imageInput} onChange={upload} /></div></div>
      <div className="editor-tools">{tools.map(t => <button key={t.id} className={mode === t.id ? 'active' : ''} onClick={() => { setMode(t.id); setConnectFrom(''); setLinkFor(null); if (t.id === 'node') { setSelected(''); setSelectedNode(null); } }}><t.icon size={15} />{t.label}</button>)}</div>
      <div className="editor-instruction">{linkFor ? `${linkFor}의 연결 통로로 쓸 지점을 지도에서 누르세요(${floor}층 복도·계단·엘리베이터). 빈 곳을 누르면 취소됩니다.` : mode === 'move' ? '쓰레기통이나 지점을 눌러 오른쪽에서 정보를 바꾸거나, 지도 위의 쓰레기통·지점을 드래그해 이동하세요.' : mode === 'add-bin' ? '새 쓰레기통을 놓을 위치를 클릭하세요.' : mode === 'node' ? placingName ? `놓을 지점: ${placingName} · 지도를 누르면 ${floor}층에 놓입니다. 이미 있는 지점을 다시 누르면 지워집니다.` : '오른쪽에서 놓을 지점을 고르세요.' : connectFrom ? `${connectFrom} 선택됨 · 연결할 두 번째 지점을 클릭하세요. 층을 변경할 수도 있습니다.` : '연결할 두 지점을 순서대로 클릭하세요.'}</div>
      <MapView workspace={mapState} floor={floor} selectedBin={selected} selectedNodes={[connectFrom, selectedNode ?? '', bin ? accessDraft : ''].filter(Boolean)} showGraph editing={mode === 'move'} onMove={move} onPlace={place} onBinClick={pick} onNodeClick={id => { if (linkFor) linkTo(id); else if (mode === 'connect') connect(id); else if (mode === 'node') removeNode(id); else if (mode === 'move') { setSelected(''); setSelectedNode(id); } }} />
      <div className="editor-floor-bins">{graph.nodes.filter(n => n.floor === floor && !walkable(n)).map(n => { const Icon = placeIcon[n.kind as PlaceKind]; return <button key={n.id} className={selectedNode === n.id ? 'active' : ''} onClick={() => { setMode('move'); setSelected(''); setSelectedNode(n.id); }}><Icon size={14} />{n.label}</button>; })}{s.bins.filter(b => b.floor === floor).map(b => <button key={b.id} className={selected === b.id && !node ? 'active' : ''} onClick={() => pick(b.id)}>{b.id}</button>)}</div>
    </section><aside className="editor-sidebar panel">
      {node ? (() => {
        const links = graph.edges.filter(e => e.from === node.id || e.to === node.id)
          .map(e => ({ e, other: graph.nodes.find(n => n.id === (e.from === node.id ? e.to : e.from)) })).filter(l => l.other);
        return <><SectionTitle title={node.label} description={`${node.floor}층 ${kindName[node.kind]} · 지도 표시 ${shortCode(node)}${node.closed ? ' · 이 층 운영 중단' : ''}`} />
          <form className="editor-form" key={`node-${node.id}-${node.label}-${node.kind}-${node.x}-${node.y}`} onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); updateNode(node, String(f.get('label')).trim() || node.label, (f.get('kind') as GraphNode['kind'] | null) ?? node.kind, Number(f.get('x')), Number(f.get('y'))); }}>
            <label>이름<input name="label" defaultValue={node.label} maxLength={40} required /></label>
            {!isCore(node) && <label>종류<select name="kind" defaultValue={node.kind}>{placeKinds.map(k => <option key={k} value={k}>{kindName[k]}</option>)}</select></label>}
            <div className="form-two"><label>X 위치<input name="x" type="number" min="0" max="100" step="0.1" defaultValue={node.x} required /></label><label>Y 위치<input name="y" type="number" min="0" max="100" step="0.1" defaultValue={node.y} required /></label></div>
            <div className="node-links"><span>이어진 지점 {links.length}개</span>{links.length ? <ul>{links.map(({ e, other }) => <li key={e.id}>{other!.floor}F · {other!.label}<button type="button" aria-label={`${other!.label} 연결 끊기`} onClick={() => setDraft({ ...graph, edges: graph.edges.filter(x => x.id !== e.id) })}><X size={13} /></button></li>)}</ul> : <p>'통로 연결' 도구로 다른 지점과 이어 주세요.</p>}</div>
            <button className="button primary full" disabled={busy}><Check size={15} />적용</button>
            <button type="button" className="button danger-text full" disabled={busy} onClick={() => removeNode(node.id)}><Trash2 size={14} />지점 삭제</button>
            <small className="node-hint">{isCore(node) ? '계단·엘리베이터 이름은 모든 층에 함께 적용됩니다. ' : ''}적용·삭제한 내용은 배치도 아래 '지점·통로 저장'을 눌러야 저장됩니다.</small>
          </form></>;
      })() : bin ? <><SectionTitle title={bin.id} description="위치와 연결 통로를 확인하세요." /><form className="editor-form" key={`${bin.id}-${bin.x}-${bin.y}-${bin.floor}`} onSubmit={e => { e.preventDefault(); mutate(`/bins/${bin.id}`, formNumbers(e.currentTarget), 'PATCH', '쓰레기통 위치를 저장했습니다.'); }}><Badge status={bin.status} /><label>위치 이름<input name="name" defaultValue={bin.name} maxLength={40} required /></label><label>층<select name="floor" defaultValue={bin.floor} onChange={e => setAccessDraft(nearest(bin.x, bin.y, +e.target.value))}>{Array.from({ length: s.building.floors }, (_, i) => <option key={i} value={i + 1}>{i + 1}층</option>)}</select></label><div className="form-two"><label>X 위치<input name="x" type="number" min="0" max="100" step="0.1" defaultValue={bin.x} required /></label><label>Y 위치<input name="y" type="number" min="0" max="100" step="0.1" defaultValue={bin.y} required /></label></div>{(() => {
        const access = graph.nodes.find(n => n.id === accessDraft), picking = linkFor === bin.id;
        return <div className="access-row"><span>연결 통로</span><div className="access-value"><strong>{access ? `${access.floor}F · ${access.label}` : '없음'}</strong><small>{picking ? '지도에서 지점을 누르세요' : accessDraft}</small></div><button type="button" className={`button small ${picking ? 'primary' : 'secondary'}`} disabled={busy} onClick={() => startLink(bin)}><Link2 size={13} />{picking ? '취소' : '연결'}</button><input type="hidden" name="access_node" value={accessDraft} readOnly /></div>;
      })()}<button className="button primary full" disabled={busy || !!draft}><Save size={15} />정보 저장</button>{bin.device_type === 'demo' && <button type="button" className="button danger-text full" disabled={busy} onClick={async () => { const r = await mutate(`/bins/${bin.id}`, {}, 'DELETE', '더미 쓰레기통을 삭제했습니다.'); if (r) setSelected(''); }}><Trash2 size={14} />더미 쓰레기통 삭제</button>}</form></>
      : <><SectionTitle title="지점 설정" description="놓을 지점을 고른 뒤 지도를 누르세요." />
        <div className="point-picker">
          <div className="point-kinds" role="radiogroup" aria-label="놓을 지점">{placeKinds.map(k => { const Icon = placeIcon[k], active = mode === 'node' && placing === k; return <button key={k} role="radio" aria-checked={active} className={active ? 'active' : ''} onClick={() => choose(k)}><Icon size={15} /><span>{kindName[k]}</span><small>{graph.nodes.filter(n => n.kind === k).length}곳</small></button>; })}</div>
          <h4>계단 · 엘리베이터</h4>
          {shaftList.length ? <div className="core-list" role="radiogroup" aria-label="놓을 계단·엘리베이터">{shaftList.map(sh => { const placed = [...sh.nodes.keys()], active = mode === 'node' && placing === sh.code; return <button key={sh.code} role="radio" aria-checked={active} className={active ? 'active' : ''} onClick={() => choose(sh.code)}><b>{sh.code}</b><span>{sh.name}</span><small>{placed.length ? `${placed.join('·')}층` : '아직 놓지 않음'}</small></button>; })}</div> : <p className="muted-note">아직 계단·엘리베이터가 없습니다.</p>}
          {placingShaft && (() => {
            const placed = [...placingShaft.nodes.keys()], kind = kindName[placingShaft.kind];
            return <form className="core-editor" key={`${placingShaft.code}-${placingShaft.name}`} onSubmit={e => { e.preventDefault(); renameShaft(placingShaft, String(new FormData(e.currentTarget).get('name')).trim()); }}>
              <label>{kind} {placingShaft.code} 이름<input name="name" defaultValue={placingShaft.name} maxLength={40} required /></label>
              <div className="core-editor-actions"><button className="button secondary small" disabled={busy}>이름 적용</button><button type="button" className="button danger-text small" disabled={busy} onClick={() => removeShaft(placingShaft)}><Trash2 size={13} />{kind} 삭제</button></div>
              <small>{placed.length ? `${placed.join('·')}층에 놓여 있습니다. 지도에서 그 층을 누르면 위치가 옮겨지고, 삭제하면 모든 층의 지점과 연결이 함께 지워집니다.` : '아직 지도에 놓지 않았습니다.'}</small>
            </form>;
          })()}
          <div className="core-add"><button className="button subtle small" onClick={() => addShaft('stairs')}><Plus size={14} />계단 추가</button><button className="button subtle small" onClick={() => addShaft('elevator')}><Plus size={14} />엘리베이터 추가</button></div>
          <small className="node-hint">계단·엘리베이터는 하나를 골라 층마다 지도에 놓으면 그 층들끼리 자동으로 이어집니다. 복도·관리자실·분리수거장은 '통로 연결' 도구로 직접 이어 주세요.</small>
        </div></>}
      <p className="editor-note">위치는 도면의 가로·세로 0~100 좌표입니다. 올린 도면은 원래 비율 그대로 가운데에 맞춰 보여 줍니다. 연결 통로부터 쓰레기통까지는 직접 접근할 수 있는 위치로 지정하세요.</p>
    </aside></div>
    <section className="panel graph-panel"><SectionTitle title="층간 이동" description="계단·엘리베이터가 서는 층과 운영 여부를 정하고, 모든 쓰레기통이 관리자실·분리수거장과 이어져 있는지 확인하세요." />
      <h3 className="graph-subtitle">계단 · 엘리베이터 운영 층</h3>
      <p className="muted-note">지도에 놓은 층만 체크 칸이 생깁니다(– = 놓지 않음). 체크를 끄면 그 층은 운영 중단으로, 그 층에서는 타고 내릴 수 없고 위아래 층끼리 바로 이어집니다.</p>
      {shaftList.length ? <div className="table-scroll"><table className="shaft-table" style={{ minWidth: 620 + floorNumbers.length * 60 }}><colgroup><col className="shaft-name" /><col className="shaft-kind" />{floorNumbers.map(f => <col key={f} className="shaft-floor" />)}<col /></colgroup><thead><tr><th>이름</th><th>종류</th>{floorNumbers.map(f => <th key={f}>{f}F</th>)}<th>상태</th></tr></thead><tbody>{shaftList.map(sh => {
        const placed = [...sh.nodes.keys()], open = placed.filter(f => !sh.nodes.get(f)!.closed), closed = placed.filter(f => sh.nodes.get(f)!.closed);
        const stopped = closed.length ? ` · ${closed.join(', ')}F 운영 중단` : '';
        const state = !placed.length ? '아직 지도에 놓지 않음' : open.length < 2 ? `다른 층과 이어지지 않음${stopped}` : `${open.join('·')}F 운행${stopped}`;
        return <tr key={sh.code}><td><strong>{sh.name}</strong> <small>{sh.code}</small></td><td>{kindName[sh.kind]}</td>{floorNumbers.map(f => { const stop = sh.nodes.get(f); return <td key={f}>{stop ? <input type="checkbox" aria-label={`${sh.name} ${f}층 운영`} checked={!stop.closed} disabled={busy} onChange={e => setDraft(setStopOpen(graph, sh, f, e.target.checked, s.graph))} /> : <span className="shaft-none" title="이 층에는 놓지 않았습니다">–</span>}</td>; })}<td className={open.length < 2 ? 'shaft-warn' : ''} title={state}>{state}</td></tr>;
      })}</tbody></table></div> : <p className="muted-note">아직 계단·엘리베이터가 없습니다. 오른쪽 '지점 설정'에서 계단 또는 엘리베이터를 추가하고 지도에 놓으세요.</p>}
      <div className={`link-check ${check.problems.length ? 'warn' : 'ok'}`}>
        {check.problems.length ? <><strong><AlertCircle size={16} />이어지지 않은 곳이 {check.problems.length}곳 있습니다</strong><ul>{check.problems.map(p => <li key={p.text}>{p.text}{p.bins.length ? ` (${p.bins.join(', ')})` : ''}</li>)}</ul></> : <strong><Check size={16} />쓰레기통 {check.binCount}개{check.depots ? '와 분리수거장' : ''}이 모두 관리자실과 이어져 있습니다.</strong>}
        {check.loose.length > 0 && <p>연결선이 하나도 없는 지점 {check.loose.length}개: {check.loose.map(n => `${n.floor}F ${n.label}`).join(', ')}</p>}
      </div>
    </section>
    {draft && <div className="draft-bar floating" role="status"><span><AlertCircle size={15} />저장하지 않은 지점·통로 변경 사항이 있습니다.</span><button className="button subtle small" onClick={() => { setDraft(null); setConnectFrom(''); }}>취소</button><button className="button primary small" disabled={busy} onClick={async () => { const r = await mutate('/graph', draft, 'PUT', '지점과 통로를 저장했습니다.'); if (r) { setDraft(null); setPending([]); } }}><Save size={14} />지점·통로 저장</button></div>}
    {newBin && <Dialog title="쓰레기통 추가" subtitle={`${floor}층 · X ${newBin.x}, Y ${newBin.y}`} onClose={() => setNewBin(null)}><form className="standard-form" onSubmit={addBin}><label>위치 이름<input name="name" required placeholder="예: 301호 앞 복도" maxLength={40} /></label><fieldset className="compartment-inputs"><legend>칸별 시연 적재율 (%)</legend>{compartments.map(c => <label key={c}>{compartmentName[c]}<input name={c} type="number" min="0" max="100" defaultValue={c === 'PET' ? 50 : 20} required /></label>)}</fieldset><label>연결 통로<select name="access_node" defaultValue={nearest(newBin.x, newBin.y)}>{floorNodes.map(n => <option key={n.id} value={n.id}>{n.label} ({n.id})</option>)}</select></label><div className="modal-actions"><button type="button" className="button secondary" onClick={() => setNewBin(null)}>취소</button><button className="button primary" disabled={busy}><Plus size={15} />추가하기</button></div></form></Dialog>}
  </>;
}

export function TeamPage(props: PageProps) {
  const { s, busy, mutate } = props;
  const offices = s.graph.nodes.filter(n => n.kind === 'office');
  const base = offices.length === 1 ? `${offices[0].floor}층 ${offices[0].label}` : offices.length ? `관리자실 ${offices.length}곳` : '관리자실 없음';
  const startOf = (id?: string) => s.graph.nodes.find(n => n.id === id);
  return <><PageHeading eyebrow="TEAM & COLLECTION" title="함께 나누면 더 가벼워져요">수거 가능한 인원에 맞춰 담당 쓰레기통과 이동 경로를 배분합니다.</PageHeading>
    <div className="team-summary panel"><div className="team-summary-copy"><span className="office-icon"><Home size={25} /></span><div><span className="eyebrow">COLLECTION BASE</span><h2>{base}</h2><p>{offices.length > 1 ? '관리자마다 첫 수거 장소에서 가장 가까운 관리자실에서 출발합니다.' : offices.length ? '모든 관리자가 이곳에서 출발합니다.' : '건물·배치도의 지점 설정에서 관리자실을 놓아 주세요.'}</p></div></div><form className="team-count-form" key={s.building.total_staff} onSubmit={e => { e.preventDefault(); const total = Number(new FormData(e.currentTarget).get('total')); mutate('/config', { total_staff: total, available_staff: Math.min(total, s.building.available_staff) }, 'PATCH', '관리자 수를 저장했습니다.'); }}><label>전체 관리자 수<input type="number" name="total" min="1" max="12" defaultValue={s.building.total_staff} required /></label><button className="button secondary" disabled={busy}>저장</button></form></div>
    <div className="team-grid">{Array.from({ length: s.building.total_staff }, (_, i) => { const r = s.last_plan?.routes.find(r => r.worker === i + 1); const available = i < s.building.available_staff; return <div className={`team-card panel ${!available ? 'unavailable' : ''}`} key={i}><div className="team-card-head"><span className="worker-avatar" style={r ? { color: r.color, background: `${r.color}15` } : {}}><Users size={19} /></span><span className={`status-badge ${available ? 'normal' : 'offline'}`}><i />{available ? '수거 가능' : '대기'}</span></div><h3>관리자 {i + 1}</h3><p>시연용 담당 번호 · {r && startOf(r.start) ? `${startOf(r.start)!.floor}층 ${startOf(r.start)!.label} 출발` : base}</p><div className="team-card-stats"><span>담당 쓰레기통<strong>{r?.bin_ids.length || 0}<small>개</small></strong></span><span>예상 작업 시간<strong>{r ? duration(r.duration_seconds) : '—'}</strong></span></div></div>; })}</div>
    <div className="notice team-notice"><Users size={17} /><span>아래에서 수거 가능 인원을 조절하세요. 이동 시간과 수거 시간을 함께 고려해 작업이 한 사람에게 몰리지 않도록 배정합니다.</span></div><RoutePanel {...props} /></>;
}

export function HistoryPage({ s }: PageProps) {
  const [query, setQuery] = useState(''); const [date, setDate] = useState('');
  const localDay = (value: string) => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul' }).format(new Date(value));
  const rows = s.logs.filter(l => (!query || `${l.bin_id} ${l.name} ${l.actor}`.toLowerCase().includes(query.toLowerCase())) && (!date || localDay(l.completed_at) === date));
  function download() {
    const cell = (v: unknown) => `"${String(v ?? '').replace(/^[=+@-]/, "'$&").replace(/"/g, '""')}"`;
    const contents = '\uFEFF' + [['수거 시각 (한국)', '쓰레기통', '층', '위치', '비운 칸', '담당', '데이터 구분'], ...rows.map(l => [dateTime(l.completed_at), l.bin_id, l.floor, l.name, l.emptied ? fillText(l.emptied) : `${l.fill_before}%`, l.worker ? `관리자 ${l.worker}` : l.actor, sourceText[l.source] || l.source])].map(r => r.map(cell).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([contents], { type: 'text/csv;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = 'reloop-collection-history.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <><PageHeading eyebrow="COLLECTION HISTORY" title="수거의 흐름을 기록합니다">완료한 수거 작업과 당시 쓰레기통 상태를 확인하세요.</PageHeading>
    <div className="history-summary"><div className="panel"><span>누적 수거 기록</span><strong>{s.logs.length}<small>건</small></strong></div><div className="panel"><span>오늘 완료</span><strong>{s.logs.filter(l => localDay(l.completed_at) === localDay(new Date().toISOString())).length}<small>건</small></strong></div><div className="panel"><span>실물 센서 기준 수거</span><strong>{s.logs.filter(l => l.source === 'actual').length}<small>건</small></strong></div></div>
    <section className="panel history-panel"><div className="history-toolbar"><div className="search-field"><Search size={16} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="쓰레기통 번호, 위치 검색" aria-label="수거 기록 검색" /></div><input type="date" value={date} onChange={e => setDate(e.target.value)} aria-label="수거 날짜" /><button className="button secondary" disabled={!rows.length} onClick={download}><Download size={15} />CSV 다운로드</button></div>
      {rows.length ? <div className="table-scroll"><table><thead><tr><th>수거 시각</th><th>쓰레기통</th><th>위치</th><th>비운 칸</th><th>담당</th><th>데이터 구분</th><th>상태</th></tr></thead><tbody>{rows.map(l => <tr key={l.id}><td>{dateTime(l.completed_at)}</td><td><strong>{l.bin_id}</strong></td><td>{l.floor}F · {l.name}</td><td>{l.emptied ? fillText(l.emptied) : `${l.fill_before}%`}</td><td>{l.worker ? `관리자 ${l.worker}` : l.actor}</td><td><span className="source-chip">{sourceText[l.source] || l.source}</span></td><td><span className="completed-badge"><Check size={12} />완료</span></td></tr>)}</tbody></table></div> : <Empty title={s.logs.length ? '검색 조건에 맞는 기록이 없습니다' : '첫 번째 수거를 기다리고 있어요'}>대시보드에서 쓰레기통의 수거 완료 버튼을 누르면 기록이 쌓입니다.</Empty>}<div className="table-footer">총 {rows.length}건 · 최근 1,000건까지 로컬에 보관합니다.</div></section></>;
}

export function DevicePage({ s, busy, mutate, notify }: PageProps) {
  const real = s.bins.find(b => b.device_type === 'real')!;
  const [fills, setFills] = useState<Record<Compartment, number>>(() => real.reading_source === 'simulated' ? Object.fromEntries(compartments.map(c => [c, real.compartments[c] ?? 0])) as Record<Compartment, number> : { CAN: 40, PET: 94, GLASS: 15, OTHER: 60 }); const [key, setKey] = useState(''); const [keyBusy, setKeyBusy] = useState(false); const [confirmKey, setConfirmKey] = useState(false);
  const endpoint = `${location.origin}/api/device/readings`;
  async function issueKey() { setConfirmKey(false); setKeyBusy(true); try { const result = await api<{ key: string }>('/device/key', payload({})); setKey(result.key); notify('장치 연결 키를 발급했습니다.'); } catch (e) { notify((e as Error).message, 'error'); } finally { setKeyBusy(false); } }
  async function copy(value: string) { try { await navigator.clipboard.writeText(value); notify('복사했습니다.'); } catch { notify('텍스트를 선택해 복사해 주세요.', 'error'); } }
  return <><PageHeading eyebrow="DEVICE CONNECTION" title="실물과 화면을 연결합니다">대회장에서 사용할 쓰레기통 1대의 측정값을 연결하고 수신 상태를 확인하세요.</PageHeading>
    <div className="device-grid"><section className="panel real-device-panel"><div className="real-device-top"><span className="eyebrow">PHYSICAL DEVICE · 01</span><Badge status={real.status} /></div><div className="real-device-hero"><BinArt fill={real.fill} status={real.status} large /><div><h2>{real.id}</h2><p>{real.floor}층 {real.name}</p><strong>{real.fill === null ? '—' : real.fill}<small>%</small></strong></div></div><CompartmentRow values={real.compartments} building={s.building} large /><SensorNotice bin={real} details /><div className="device-source-label"><Radio size={15} />{sourceText[real.reading_source]}</div><div className="detail-info"><div><span>마지막 측정</span><strong>{dateTime(real.measured_at)}</strong></div><div><span>서버 수신</span><strong>{dateTime(real.received_at)}</strong></div><div><span>수신 지연 기준</span><strong>{s.building.stale_minutes}분</strong></div></div><p className="muted-note">화면은 5초마다 갱신됩니다. 칸별로 오래된 값은 수신 대기로 표시하고, 현재 적재율·경로·수거량 계산에서 제외합니다.</p></section>
      <section className="panel simulation-panel"><SectionTitle eyebrow="DEMO CONTROL" title="실물 위치 시뮬레이션" description="센서 연결 전에도 상태 변화와 수거 경로를 시연할 수 있습니다." />{compartments.map(c => <label key={c} className="compartment-slider"><span>{compartmentName[c]}</span><input type="range" min="0" max="100" value={fills[c]} onChange={e => setFills({ ...fills, [c]: +e.target.value })} aria-label={`${compartmentName[c]} 칸 시뮬레이션 적재율`} /><b>{fills[c]}%</b></label>)}<div className="simulation-presets"><button onClick={() => setFills({ CAN: 30, PET: 45, GLASS: 12, OTHER: 40 })}><i className="normal" />정상</button><button onClick={() => setFills({ CAN: 55, PET: 85, GLASS: 20, OTHER: 62 })}><i className="warning" />주의</button><button onClick={() => setFills({ CAN: 96, PET: 82, GLASS: 30, OTHER: 70 })}><i className="critical" />수거 필요</button></div><button className="button primary full" disabled={busy} onClick={() => mutate('/demo/real-simulation', { fills }, 'POST', '시뮬레이션 값을 적용했습니다.')}><Sparkles size={16} />시뮬레이션 적용</button>{real.reading_source === 'simulated' && <button className="button subtle full" disabled={busy} onClick={() => mutate('/demo/real-simulation', { fills: null }, 'POST', '실물 센서 연결을 기다립니다.')}>시뮬레이션 종료</button>}<div className="notice"><AlertCircle size={16} /><span>시뮬레이션 값에는 별도 표시가 붙습니다. 실제 센서값을 받으면 자동으로 실물 모드로 전환됩니다.</span></div></section></div>
    <section className="panel device-setup"><SectionTitle title="센서 연결 설정" description="게이트웨이 또는 센서 장치에서 아래 주소로 적재율을 전송하세요." /><div className="setup-steps"><div className="setup-step"><span className="step-number">1</span><div><h3>장치 연결 키 발급</h3><p>연결 키는 현재 계정의 실물 쓰레기통에만 사용할 수 있습니다.</p><button className="button secondary" disabled={keyBusy} onClick={() => s.device_key_hint || key ? setConfirmKey(true) : issueKey()}><KeyRound size={15} />{s.device_key_hint || key ? '연결 키 다시 발급' : '연결 키 발급'}</button>{key && <div className="secret-display"><code>{key}</code><button className="icon-button" aria-label="장치 연결 키 복사" onClick={() => copy(key)}><Copy size={15} /></button></div>}{!key && s.device_key_hint && <span className="key-hint">발급된 키 끝자리 · {s.device_key_hint}</span>}{key && <p className="key-hint">전체 키는 현재 화면에서만 확인할 수 있습니다. 장치 설정에 복사해 주세요.</p>}</div></div>
      <div className="setup-step"><span className="step-number">2</span><div><h3>전송 주소 확인</h3><div className="endpoint"><span>POST</span><code>{endpoint}</code><button className="icon-button" aria-label="전송 주소 복사" onClick={() => copy(endpoint)}><Copy size={15} /></button></div><p>다른 기기의 센서는 같은 네트워크에서 서버 PC의 IP 주소를 사용합니다. 실행 안내의 LAN 모드로 서버를 시작해 주세요.</p></div></div>
      <div className="setup-step"><span className="step-number">3</span><div><h3>측정값 전송</h3><p>요청 헤더의 <code>X-Device-Key</code>에 발급한 키를 넣고, 칸 하나씩 또는 여러 칸을 한 번에 전송합니다.</p><pre className="code-block">{JSON.stringify({ bin_id: real.id, compartment: 'PET', fill_percent: 94 }, null, 2)}</pre><pre className="code-block">{JSON.stringify({ bin_id: real.id, fills: { CAN: 40, PET: 94, GLASS: 15, OTHER: 60 } }, null, 2)}</pre><p className="muted-note">칸은 CAN(캔) · PET · GLASS(유리) · OTHER(일반)이고, 적재율은 0~100입니다. 측정 시각(measured_at)을 생략하면 서버 수신 시각을 사용합니다.</p></div></div></div></section>
    <section className="panel readings-panel"><SectionTitle title="최근 수신 기록" description="실제 측정과 시뮬레이션을 구분해 표시합니다." />{s.readings.length ? <div className="table-scroll"><table><thead><tr><th>수신 시각</th><th>쓰레기통</th><th>적재율</th><th>출처</th></tr></thead><tbody>{s.readings.slice(0, 10).map((r, i) => <tr key={`${r.at}-${i}`}><td>{dateTime(r.at)}</td><td>{r.bin_id}</td><td>{r.fills ? fillText(r.fills) : r.fill === null ? '연결 대기' : `${r.fill}%`}</td><td><span className="source-chip">{sourceText[r.source]}</span></td></tr>)}</tbody></table></div> : <Empty title="아직 수신한 기록이 없습니다">센서를 연결하거나 시뮬레이션을 적용해 보세요.</Empty>}</section>
    {confirmKey && <Dialog title="장치 연결 키를 다시 발급할까요?" onClose={() => setConfirmKey(false)}><p className="dialog-copy">새 키를 발급하면 이전 키는 만료됩니다. 연결된 센서의 키도 새 값으로 변경해 주세요.</p><div className="modal-actions"><button className="button secondary" onClick={() => setConfirmKey(false)}>취소</button><button className="button primary" onClick={issueKey}>새 키 발급</button></div></Dialog>}
  </>;
}

export function SettingsPage({ s, busy, mutate, notify }: PageProps) {
  const [reset, setReset] = useState<'' | 'basic' | 'large' | 'library' | 'civic' | 'round'>('');
  const samples = { large: '큰 건물 예시', library: '도서관 예시', civic: '복합청사 예시', round: '곡선형 건물 예시' } as const; const [restore, setRestore] = useState<Record<string, unknown> | null>(null);
  const restoreInput = useRef<HTMLInputElement>(null);
  async function selectRestore(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
    if (file.size > 35_000_000) { notify('백업은 35MB 이하로 선택해 주세요.', 'error'); return; }
    try { const data = JSON.parse(await file.text()); if (data.format !== 'reloop-backup-v1') throw new Error(); setRestore(data); } catch { notify('리루프 백업 파일을 선택해 주세요.', 'error'); }
  }
  return <><PageHeading eyebrow="WORKSPACE SETTINGS" title="운영 기준을 조정하세요">상태 기준과 이동 조건을 설정하고, 로컬 데이터를 보관합니다.</PageHeading>
    <form className="panel settings-form" key={[s.building.warning_threshold, s.building.critical_threshold, s.building.meters_per_unit, s.building.stairs_up_seconds, s.building.stairs_down_seconds, s.building.elevator_wait_seconds, s.building.elevator_floor_seconds, s.building.use_cart, s.building.cart_capacity, s.building.unload_seconds, s.building.compartment_seconds, s.building.max_work_minutes].join('-')} onSubmit={e => { e.preventDefault(); const form = e.currentTarget; mutate('/config', { ...formNumbers(form), use_cart: (form.elements.namedItem('use_cart') as HTMLInputElement).checked }, 'PATCH', '운영 기준을 저장했습니다.'); }}><SectionTitle title="쓰레기통 상태 기준" description="설정한 적재율을 기준으로 카드 색상과 수거 대상을 결정합니다." /><div className="settings-fields"><label><span><i className="settings-dot warning" />주의 시작 (%)</span><input name="warning_threshold" type="number" min="1" max="99" defaultValue={s.building.warning_threshold} required /></label><label><span><i className="settings-dot critical" />수거 필요 시작 (%)</span><input name="critical_threshold" type="number" min="2" max="100" defaultValue={s.building.critical_threshold} required /></label><label>센서 수신 지연 기준 (분)<input name="stale_minutes" type="number" min="1" max="120" defaultValue={s.building.stale_minutes} required /></label></div><div className="settings-rule" /><SectionTitle title="경로와 예상 시간" description="대회용 기본값입니다. 실제 도면을 사용한다면 축척을 맞춰 주세요." /><div className="settings-fields"><label>도면 1단위당 거리 (m)<input name="meters_per_unit" type="number" min="0.05" max="10" step="0.05" defaultValue={s.building.meters_per_unit} required /><small>가로 1칸 기준(기본 0.6m · 가로 전체 60m) · 세로는 화면 비율대로 계산합니다</small></label><label>보행 속도 (m/s)<input name="speed_mps" type="number" min="0.2" max="3" step="0.1" defaultValue={s.building.speed_mps} required /></label><label>위치당 기본 수거 시간 (초)<input name="service_seconds" type="number" min="0" max="600" defaultValue={s.building.service_seconds} required /><small>여기에 비우는 칸마다 칸 수거 시간을 더합니다</small></label></div>
      <div className="settings-rule" /><SectionTitle title="이동과 수거 조건" description="동선은 이 시간들로 계산합니다. 기본값은 가정이니 현장에서 재서 맞춰 주세요." /><div className="settings-fields">
        <label>계단 오르기 (초/층)<input name="stairs_up_seconds" type="number" min="1" max="300" step="1" defaultValue={s.building.stairs_up_seconds ?? 20} required /></label>
        <label>계단 내려가기 (초/층)<input name="stairs_down_seconds" type="number" min="1" max="300" step="1" defaultValue={s.building.stairs_down_seconds ?? 14} required /></label>
        <label>엘리베이터 기다리기 (초)<input name="elevator_wait_seconds" type="number" min="0" max="600" step="1" defaultValue={s.building.elevator_wait_seconds ?? 40} required /><small>탈 때마다 한 번 더합니다</small></label>
        <label>엘리베이터 층당 이동 (초)<input name="elevator_floor_seconds" type="number" min="0.5" max="120" step="0.5" defaultValue={s.building.elevator_floor_seconds ?? 4} required /></label>
        <label>한 번에 옮길 양 (가득 찬 칸 개수)<input name="cart_capacity" type="number" min="0" max="50" step="0.5" defaultValue={s.building.cart_capacity ?? 4} required /><small>위치 사이에서 용량이 차면 비웁니다. 한 위치의 수거량이 용량을 넘으면 계산을 중단합니다 · 0이면 제한 없음</small></label>
        <label>분리수거장에서 비우는 시간 (초)<input name="unload_seconds" type="number" min="0" max="600" defaultValue={s.building.unload_seconds ?? 60} required /></label>
        <label>칸 하나 수거 시간 (초)<input name="compartment_seconds" type="number" min="0" max="600" defaultValue={s.building.compartment_seconds ?? 15} required /><small>주의 기준 이상인 칸을 함께 비웁니다</small></label>
        <label>한 사람 작업 시간 상한 (분)<input name="max_work_minutes" type="number" min="0" max="480" defaultValue={s.building.max_work_minutes ?? 20} required /><small>'인력 아끼기'가 이 안에서 인원을 줄입니다 · 0이면 제한 없음</small></label>
        <label className="settings-check"><input name="use_cart" type="checkbox" defaultChecked={!!s.building.use_cart} /><span>수거 카트 사용<small>계단 대신 엘리베이터만 쓰고, 걷는 속도는 85%로 계산합니다</small></span></label>
      </div><div className="settings-save"><span><ShieldCheck size={14} />설정은 현재 계정의 건물에 적용됩니다.</span><button className="button primary" disabled={busy}><Save size={16} />설정 저장</button></div></form>
    <div className="settings-bottom-grid"><section className="panel backup-panel"><SectionTitle title="데이터 백업 · 복원" description="건물 배치, 운영 설정과 수거 기록을 파일로 보관하세요." /><div className="backup-illustration"><Download size={32} /><div><strong>내 건물의 기록을 안전하게</strong><span>계정 비밀번호와 장치 연결 키는 포함하지 않습니다.</span></div></div><div className="inline-actions"><a className="button secondary" href="/api/backup" download><Download size={15} />백업 다운로드</a><button className="button secondary" disabled={busy} onClick={() => restoreInput.current?.click()}><Upload size={15} />백업 복원</button><input ref={restoreInput} type="file" accept=".json,application/json" onChange={selectRestore} hidden /></div></section>
      <section className="panel reset-panel"><SectionTitle title="대회 시연 초기화" description="다음 시연을 위해 예시 건물을 처음 상태로 되돌립니다." /><p>현재 배치와 수거 기록은 초기화됩니다.</p><ul className="sample-list"><li><b>기본 건물</b>3층 · 쓰레기통 12개 · 관리자 3명</li><li><b>큰 건물</b>5층 · 복도 2개 · 계단 2곳 · 엘리베이터 1대 · 쓰레기통 30개 · 관리자 5명</li><li><b>도서관</b>6층 · 아트리움을 둘러싼 고리형 복도 · 엘리베이터 2대 · 관리자실 2곳 · 쓰레기통 45개 · 관리자 6명</li><li><b>복합청사</b>8층 행정동과 5층 문화복지동 · 계단 3곳 · 엘리베이터 2대 · 분리수거장 2곳 · 쓰레기통 79개 · 관리자 8명</li><li><b>곡선형</b>4층 트랙 모양 컨벤션센터 · 곡선 복도 2겹과 방사형 통로 · 쓰레기통 61개 · 관리자 8명</li></ul><div className="inline-actions"><button className="button danger-text" disabled={busy} onClick={() => setReset('basic')}><RefreshCw size={15} />기본 건물로 초기화</button><button className="button secondary" disabled={busy} onClick={() => setReset('large')}><Building2 size={15} />큰 건물 예시로 바꾸기</button><button className="button secondary" disabled={busy} onClick={() => setReset('library')}><Building2 size={15} />도서관 예시로 바꾸기</button><button className="button secondary" disabled={busy} onClick={() => setReset('civic')}><Building2 size={15} />복합청사 예시로 바꾸기</button><button className="button secondary" disabled={busy} onClick={() => setReset('round')}><Building2 size={15} />곡선형 건물 예시로 바꾸기</button></div></section></div>
    {reset && <Dialog title={reset === 'basic' ? '시연 데이터를 초기화할까요?' : `${samples[reset]}로 바꿀까요?`} subtitle="현재 계정의 건물 배치와 수거 기록이 예시 데이터로 바뀝니다." onClose={() => setReset('')}><p className="dialog-copy">보관할 내용이 있다면 먼저 백업해 주세요. 로그인 계정과 발급된 장치 연결 키는 유지됩니다.</p><div className="modal-actions"><button className="button secondary" onClick={() => setReset('')}>취소</button><button className="button primary" disabled={busy} onClick={async () => { const r = await mutate('/demo/reset', { template: reset }, 'POST', reset === 'basic' ? '시연 데이터를 초기화했습니다.' : `${samples[reset]}로 바꿨습니다.`); if (r) setReset(''); }}>{reset === 'basic' ? '초기화' : '바꾸기'}</button></div></Dialog>}
    {restore && <Dialog title="백업으로 복원할까요?" subtitle="현재 건물 배치·설정·수거 기록을 백업 내용으로 교체합니다." onClose={() => setRestore(null)}><p className="dialog-copy">실물 센서는 복원 후 새로운 측정값을 기다립니다. 로그인 계정과 현재 장치 연결 키는 유지됩니다.</p><div className="modal-actions"><button className="button secondary" onClick={() => setRestore(null)}>취소</button><button className="button primary" disabled={busy} onClick={async () => { const r = await mutate('/restore', restore, 'POST', '백업을 복원했습니다.'); if (r) setRestore(null); }}>복원하기</button></div></Dialog>}
  </>;
}
